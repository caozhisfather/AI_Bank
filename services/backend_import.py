"""Administrative, filesystem-only ingestion of complete business table snapshots."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np

from carbon_finance.config import FEATURE_COLUMNS
from carbon_finance.data import load_demo_data
from carbon_finance.lmdi import decompose_lmdi
from carbon_finance.pipeline import CarbonFinancePipeline
from services.business_store import BusinessStore, encoded, now


def prepare_snapshot(source_dir):
    source_dir = Path(source_dir).resolve()
    data = load_demo_data(source_dir)
    companies, features, energy = (data[key] for key in ("companies", "features", "energy"))
    for name, frame, required in (
        ("companies", companies, ["company_id", "company_name", "industry", "base_limit", "project_need"]),
        ("features", features, ["company_id", "company_name", "shock_sensitivity", *FEATURE_COLUMNS]),
        ("energy", energy, ["company_id", "period", "energy_type", "output", "energy", "emission_factor"]),
        ("training", data["training"], [*FEATURE_COLUMNS, "target_met"]),
        ("network", data["network"], ["source", "target", "weight"]),
    ):
        missing = set(required) - set(frame.columns)
        if missing:
            raise ValueError(f"{name} 缺少字段：{', '.join(sorted(missing))}")
        if frame[required].isna().any().any():
            raise ValueError(f"{name} 的必填字段存在空值")
    ids = set(companies.company_id)
    if not ids or companies.company_id.duplicated().any() or features.company_id.duplicated().any():
        raise ValueError("企业编号不能为空或重复")
    if ids != set(features.company_id) or ids != set(energy.company_id):
        raise ValueError("企业名录、转型指标与能耗记录的企业编号不一致")
    if energy.duplicated(["company_id", "period", "energy_type"]).any():
        raise ValueError("同企业、同期间、同能源存在重复记录")
    if not energy.period.astype(str).map(lambda value: bool(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value))).all():
        raise ValueError("报告期间须为 YYYY-MM")
    if (energy.period.astype(str) > datetime.now(timezone.utc).strftime("%Y-%m")).any():
        raise ValueError("不能导入尚未发生的报告期间")
    for frame, columns, strictly_positive in (
        (energy, ["output", "energy", "emission_factor"], True),
        (companies, ["base_limit", "project_need"], False),
        (features, [*FEATURE_COLUMNS, "shock_sensitivity"], None),
        (data["training"], FEATURE_COLUMNS, None),
        (data["network"], ["weight"], False),
    ):
        values = frame[columns].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("数值字段必须为有限数值")
        if strictly_positive is True and (values <= 0).any():
            raise ValueError("产量、能耗与排放因子必须大于零")
        if strictly_positive is False and (values < 0).any():
            raise ValueError("金额和关联权重不能为负数")
    if (data["network"].weight > 1).any():
        raise ValueError("关联权重不能超过 1")
    for column in ("project_progress", "fund_usage_match", "own_fund_arrival", "data_completeness", "energy_cost_ratio"):
        if not features[column].between(0, 1).all():
            raise ValueError(f"{column} 必须位于 0 到 1")
    support = data.get("support_nodes")
    node_ids = ids | (set(support.company_id) if support is not None and not support.empty else set())
    if not (set(data["network"].source) | set(data["network"].target)) <= node_ids:
        raise ValueError("关联网络存在未登记的企业或支撑节点")
    if not energy.groupby(["company_id", "period"]).output.nunique().eq(1).all():
        raise ValueError("同企业同期间的各能源记录必须使用相同产量")
    for company_id in ids:
        subset = energy.loc[energy.company_id.eq(company_id)]
        periods = sorted(subset.period.unique())
        if len(periods) < 2:
            raise ValueError(f"{company_id} 至少需要两个报告期的能耗记录")
        decompose_lmdi(subset.loc[subset.period.isin([periods[0], periods[-1]])])
    # Validate that the imported snapshot can actually be consumed by the production engines.
    CarbonFinancePipeline(data=data).run("正常情景")
    manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(source_dir.glob("*.csv"))}
    digest = hashlib.sha256(encoded(manifest).encode()).hexdigest()
    return data, {"digest": digest, "files": manifest, "company_count": len(ids),
                  "energy_records": len(energy), "relationship_count": len(data["network"])}


def import_snapshot(source_dir, database, source_label, *, apply=False, backup_dir=None):
    """Validate by default; applying requires an explicit CLI switch, never a web route."""
    if not source_label or not source_label.strip() or len(source_label) > 200:
        raise ValueError("需要提供不超过 200 字的数据来源说明")
    data, manifest = prepare_snapshot(source_dir)
    result = {"applied": False, "source": source_label.strip(), **manifest}
    if not apply:
        return {**result, "mode": "validation_only"}
    database = Path(database).resolve()
    backup_root = Path(backup_dir or database.parent / "import-backups")
    batch_id = "IMPORT-" + uuid4().hex[:12].upper()
    backup = backup_root / f"{batch_id}.db"
    store = BusinessStore(database)
    with store.lock, store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""CREATE TABLE IF NOT EXISTS backend_import_batches (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, source TEXT NOT NULL,
            digest TEXT NOT NULL UNIQUE, manifest TEXT NOT NULL, previous_reference TEXT NOT NULL)""")
        existing = db.execute("SELECT id FROM backend_import_batches WHERE digest=?", (manifest["digest"],)).fetchone()
        if existing:
            return {**result, "batch_id": existing["id"], "mode": "already_imported"}
        old_ids = {row[0] for row in db.execute("SELECT company_id FROM company_heads")}
        new_ids = set(data["companies"].company_id)
        if not old_ids <= new_ids:
            raise ValueError("完整快照缺少已有企业；为保留历史数据，未执行导入")
        if database.exists():
            backup_root.mkdir(parents=True, exist_ok=True)
            # A second read connection backs up the last committed state while the writer is reserved.
            with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
                source.backup(target)
        previous = [dict(row) for row in db.execute("SELECT * FROM business_reference")]
        db.execute("INSERT INTO backend_import_batches VALUES(?,?,?,?,?,?)",
                   (batch_id, now(), source_label.strip(), manifest["digest"], encoded(manifest), encoded(previous)))
        for key, frame in data.items():
            db.execute("INSERT INTO business_reference VALUES(?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                       (key, frame.to_json(orient="records", force_ascii=False, double_precision=15)))
        records = {key: json.loads(frame.to_json(orient="records", force_ascii=False, double_precision=15))
                   for key, frame in data.items() if key in ("companies", "features", "energy")}
        features = {row["company_id"]: row for row in records["features"]}
        for company in records["companies"]:
            company_id = company["company_id"]
            energy = [row for row in records["energy"] if row["company_id"] == company_id]
            payload = {"company": company, "features": features[company_id], "energy": energy}
            store._insert_version(db, company_id, payload, max(row["period"] for row in energy),
                                  f"后台导入 · {source_label.strip()} · {batch_id}")
    return {**result, "applied": True, "batch_id": batch_id, "backup": str(backup), "mode": "applied"}
