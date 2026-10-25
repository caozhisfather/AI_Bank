from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

import pandas as pd

from carbon_finance.config import DATA_DIR
from carbon_finance.data import load_demo_data, load_mitigation_profiles
from carbon_finance.lmdi import decompose_lmdi, validate_route_records


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


class ConflictError(ValueError):
    pass


FEATURE_BOUNDS = {
    "project_progress": (0, 1), "milestone_delay_days": (0, 3650),
    "fund_usage_match": (0, 1), "own_fund_arrival": (0, 1),
    "cashflow_coverage": (0, 100), "energy_cost_ratio": (0, 1),
    "data_completeness": (0, 1),
}
OPEN_STATUSES = ("awaiting_material", "pending_review", "returned", "tracking")


def revise_payload(previous: dict, patch: dict, period: str) -> dict:
    """Validate enterprise-owned fields; bank credit and relation data stay read-only."""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        raise ValueError("报告期间须为 YYYY-MM")
    unknown = set(patch) - {"features", "energy_records", "route_records"}
    if unknown:
        raise ValueError(f"不支持修改字段：{', '.join(sorted(unknown))}")
    payload = copy.deepcopy(previous)
    features = patch.get("features", {})
    if not isinstance(features, dict) or set(features) - FEATURE_BOUNDS.keys():
        raise ValueError("仅可更新项目、资金、经营与完整度指标")
    for key, value in features.items():
        low, high = FEATURE_BOUNDS[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} 必须为 {low} 到 {high} 之间的有限数值")
        payload["features"][key] = value
    records = patch.get("energy_records")
    if records is not None:
        if not isinstance(records, list) or not 1 <= len(records) <= 20:
            raise ValueError("每期需提交 1–20 条能耗记录")
        expected = {row["energy_type"] for row in payload["energy"] if row["period"] == max(item["period"] for item in payload["energy"])}
        types, outputs, checked = set(), set(), []
        for row in records:
            if not isinstance(row, dict) or set(row) != {"energy_type", "energy", "output", "emission_factor"}:
                raise ValueError("能耗记录需包含 energy_type、energy、output、emission_factor")
            if row["energy_type"] not in expected or row["energy_type"] in types:
                raise ValueError("能源类型未知或重复")
            types.add(row["energy_type"])
            for key in ("energy", "output", "emission_factor"):
                value = row[key]
                if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 < value <= 1e12:
                    raise ValueError(f"{key} 必须为大于零的有限数值")
            outputs.add(row["output"])
            checked.append({**row, "company_id": payload["company"]["company_id"], "period": period})
        if types != expected or len(outputs) != 1:
            raise ValueError("需提交完整能源类型，且同一期产量必须一致")
        payload["energy"] = [row for row in payload["energy"] if row["period"] != period] + checked
        frame = pd.DataFrame(payload["energy"])
        periods = sorted(frame.period.unique())
        effects = decompose_lmdi(frame.loc[frame.period.isin([periods[0], periods[-1]])])
        technical = max(0, -effects["efficiency"]) + max(0, -effects["energy_structure"])
        denominator = max(technical, abs(effects["total_change"]), 1e-9)
        payload["features"]["lmdi_efficiency_share"] = max(0, -effects["efficiency"]) / denominator
        payload["features"]["lmdi_energy_share"] = max(0, -effects["energy_structure"]) / denominator
        first = frame.loc[frame.period == periods[0]]
        last = frame.loc[frame.period == periods[-1]]
        base_intensity = float((first.energy * first.emission_factor).sum() / first.output.iloc[0])
        current_intensity = float((last.energy * last.emission_factor).sum() / last.output.iloc[0])
        payload["features"]["intensity_trend"] = (base_intensity - current_intensity) / base_intensity
        payload["company"]["carbon_intensity"] = current_intensity
    routes = patch.get("route_records")
    if routes is not None:
        frame = pd.DataFrame(payload["energy"])
        checked_routes = validate_route_records(routes, frame)
        updated_periods = {row["period"] for row in checked_routes}
        payload["routes"] = [row for row in payload.get("routes", []) if row["period"] not in updated_periods] + copy.deepcopy(checked_routes)
    # An energy correction must also reconcile any previously supplied route facts.
    if payload.get("routes"):
        validate_route_records(payload["routes"], pd.DataFrame(payload["energy"]))
    if not features and not records and not routes:
        raise ValueError("至少提交一项结构化更新")
    return payload


class BusinessStore:
    """Versioned company facts, materials and review decisions; no retention pruning."""

    def __init__(self, path: Path | None = None):
        self.path = path or DATA_DIR / "runtime" / "platform.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS business_reference (name TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS company_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, company_id TEXT NOT NULL, version INTEGER NOT NULL,
                    period TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL,
                    request_id TEXT, request_hash TEXT, UNIQUE(company_id, version), UNIQUE(company_id, request_id));
                CREATE TABLE IF NOT EXISTS company_heads (company_id TEXT PRIMARY KEY, version_id INTEGER NOT NULL REFERENCES company_versions(id));
                CREATE TABLE IF NOT EXISTS business_sessions (token_hash TEXT PRIMARY KEY, account TEXT NOT NULL, role TEXT NOT NULL, company_id TEXT, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS review_tasks (
                    id TEXT PRIMARY KEY, company_id TEXT NOT NULL, version_id INTEGER NOT NULL REFERENCES company_versions(id),
                    period TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL,
                    details TEXT NOT NULL, outcome TEXT, revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(version_id, kind));
                CREATE TABLE IF NOT EXISTS evidence_submissions (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES review_tasks(id), actor TEXT NOT NULL,
                    explanation TEXT NOT NULL, corrections TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evidence_materials (
                    id TEXT PRIMARY KEY, submission_id TEXT NOT NULL REFERENCES evidence_submissions(id),
                    name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, content BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS review_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL REFERENCES review_tasks(id), actor TEXT NOT NULL,
                    action TEXT NOT NULL, comment TEXT NOT NULL, created_at TEXT NOT NULL, submission_id TEXT,
                    result TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def seed(self):
        with self.lock, self.connect() as db:
            if db.execute("SELECT 1 FROM business_reference LIMIT 1").fetchone():
                profiles = load_mitigation_profiles()
                db.execute("INSERT OR IGNORE INTO business_reference VALUES (?, ?)", ('network_mitigation', profiles.to_json(orient='records', force_ascii=False, double_precision=15)))
                return
            data = load_demo_data()
            for name, frame in data.items():
                db.execute("INSERT INTO business_reference VALUES (?, ?)", (name, frame.to_json(orient="records", force_ascii=False, double_precision=15)))
            for company in data["companies"].to_dict(orient="records"):
                company_id = company["company_id"]
                payload = {
                    "company": company,
                    "features": data["features"].loc[data["features"].company_id == company_id].iloc[0].to_dict(),
                    "energy": data["energy"].loc[data["energy"].company_id == company_id].to_dict(orient="records"),
                }
                period = max(row["period"] for row in payload["energy"])
                self._insert_version(db, company_id, payload, period, "初始演示数据迁移")

    @staticmethod
    def _version(row):
        if row is None:
            raise KeyError("企业数据不存在")
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

    def latest(self, company_id):
        with self.lock, self.connect() as db:
            return self._version(db.execute("SELECT v.* FROM company_versions v JOIN company_heads h ON h.version_id=v.id WHERE h.company_id=?", (company_id,)).fetchone())

    def _insert_version(self, db, company_id, payload, period, source, request_id=None, request_hash=None, keep_task=None):
        version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM company_versions WHERE company_id=?", (company_id,)).fetchone()[0]
        cursor = db.execute("INSERT INTO company_versions(company_id,version,period,source,created_at,payload,request_id,request_hash) VALUES(?,?,?,?,?,?,?,?)", (company_id, version, period, source, now(), encoded(payload), request_id, request_hash))
        db.execute("INSERT INTO company_heads VALUES(?,?) ON CONFLICT(company_id) DO UPDATE SET version_id=excluded.version_id", (company_id, cursor.lastrowid))
        db.execute("UPDATE review_tasks SET status='superseded', revision=revision+1, updated_at=? WHERE company_id=? AND status IN ('awaiting_material','pending_review','returned','tracking') AND id != ?", (now(), company_id, keep_task or ""))
        return cursor.lastrowid

    def load_data(self):
        with self.lock, self.connect() as db:
            data = {row["name"]: pd.DataFrame(json.loads(row["payload"])) for row in db.execute("SELECT * FROM business_reference")}
            versions = [self._version(row) for row in db.execute("SELECT v.* FROM company_versions v JOIN company_heads h ON v.id=h.version_id ORDER BY v.company_id")]
        data["companies"] = pd.DataFrame([v["payload"]["company"] for v in versions])
        data["features"] = pd.DataFrame([v["payload"]["features"] for v in versions])
        data["energy"] = pd.DataFrame([row for v in versions for row in v["payload"]["energy"]])
        data["routes"] = [dict(row, company_id=v["company_id"]) for v in versions for row in v["payload"].get("routes", [])]
        return data, versions

    def sync(self, company_id, request_id, source, period, patch):
        digest = hashlib.sha256(encoded({"source": source, "period": period, "patch": patch}).encode()).hexdigest()
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM company_versions WHERE company_id=? AND request_id=?", (company_id, request_id)).fetchone()
            if existing:
                if existing["request_hash"] != digest:
                    raise ConflictError("同一请求编号的内容发生变化，请使用新编号")
                return self._version(existing), True
            previous = self.latest(company_id)
            if period <= previous["period"]:
                raise ConflictError("已入库报告期的数据修订需通过补充材料提出更正，由银行核验后生效")
            if period > datetime.now(timezone.utc).strftime("%Y-%m"):
                raise ValueError("不能提交尚未发生的报告期间")
            if period > previous["period"] and not patch.get("energy_records"):
                raise ValueError("新报告期须同时提交完整能耗记录")
            if any(row.get("period") != period for row in (patch.get("route_records") or []) if isinstance(row, dict)):
                raise ConflictError("历史工艺明细需通过补充材料提出，由银行核验后生效")
            payload = revise_payload(previous["payload"], patch, period)
            new_id = self._insert_version(db, company_id, payload, period, source, request_id, digest)
            return self._version(db.execute("SELECT * FROM company_versions WHERE id=?", (new_id,)).fetchone()), False

    def reconcile_tasks(self, versions, evaluations):
        by_company = evaluations.set_index("company_id")
        with self.lock, self.connect() as db:
            for version in versions:
                current = db.execute("SELECT version_id FROM company_heads WHERE company_id=?", (version["company_id"],)).fetchone()
                if current[0] != version["id"]:
                    continue
                payload, company_id = version["payload"], version["company_id"]
                if payload['company'].get('evaluation_model') == 'operating':
                    continue
                feature = payload["features"]
                conditions = []
                score = float(by_company.loc[company_id, "anomaly_score"])
                if score >= 0.4:
                    conditions.append(("data_anomaly", "数据组合异常待核验", {"value": score, "threshold": 0.4, "description": "模型组合异常分数达到演示核验阈值；核验范围为当前数据版本的组合输入。"}))
                if feature["fund_usage_match"] < 0.9:
                    conditions.append(("fund_usage", "资金用途一致率偏低", {"value": feature["fund_usage_match"], "threshold": 0.9, "description": "需补充资金用途说明、合同或支付凭证；核验不抹除实际用途偏离。"}))
                if feature["milestone_delay_days"] > 15:
                    conditions.append(("milestone", "项目里程碑延期", {"value": feature["milestone_delay_days"], "threshold": 15, "description": "需补充施工计划或验收资料；实际延期仍保留在模型输入。"}))
                frame = pd.DataFrame(payload["energy"])
                frame["emissions"] = frame.energy * frame.emission_factor
                grouped = frame.groupby("period").agg(emissions=("emissions", "sum"), output=("output", "max"))
                intensities = grouped.emissions / grouped.output
                if len(intensities) > 1:
                    change = float(intensities.iloc[-1] / intensities.iloc[-2] - 1)
                    if abs(change) >= 0.15:
                        conditions.append(("energy_spike", "单位产量排放出现明显波动", {"value": change, "threshold": 0.15, "previous_period": str(intensities.index[-2]), "description": "相邻报告期单位产量排放变化达到 15% 演示阈值，需说明检修、生产调整或计量情况。", "previous_intensity": float(intensities.iloc[-2]), "current_intensity": float(intensities.iloc[-1])}))
                for kind, title, details in conditions:
                    db.execute("INSERT OR IGNORE INTO review_tasks(id,company_id,version_id,period,kind,title,status,details,created_at,updated_at) VALUES(?,?,?,?,?,?,'awaiting_material',?,?,?)", (f"RV-{uuid4().hex[:12].upper()}", company_id, version["id"], version["period"], kind, title, encoded(details), now(), now()))

    def approved_model_versions(self):
        with self.lock, self.connect() as db:
            return {row[0] for row in db.execute("SELECT t.company_id FROM review_tasks t JOIN company_heads h ON h.version_id=t.version_id WHERE t.kind='data_anomaly' AND t.status='resolved' AND t.outcome='reasonable'")}

    def tasks(self, company_id=None):
        with self.lock, self.connect() as db:
            rows = db.execute("SELECT t.*,v.version,v.source,CASE WHEN h.version_id=t.version_id THEN 1 ELSE 0 END AS is_current FROM review_tasks t JOIN company_versions v ON v.id=t.version_id JOIN company_heads h ON h.company_id=t.company_id WHERE (? IS NULL OR t.company_id=?) ORDER BY t.updated_at DESC,t.id", (company_id, company_id)).fetchall()
            companies = {row['id']: json.loads(row['payload'])['company']['company_name'] for row in db.execute('SELECT * FROM company_versions')}
            result = []
            for row in rows:
                item = dict(row); item["details"] = json.loads(item["details"]); item["company_name"] = companies[item['version_id']]
                item["submission_count"] = db.execute("SELECT COUNT(*) FROM evidence_submissions WHERE task_id=?", (item["id"],)).fetchone()[0]
                result.append(item)
            return result

    def task(self, task_id):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT company_id FROM review_tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise KeyError("审核任务不存在")
            item = next(t for t in self.tasks(row[0]) if t["id"] == task_id)
            submissions = []
            for row in db.execute("SELECT * FROM evidence_submissions WHERE task_id=? ORDER BY created_at,id", (task_id,)):
                entry = dict(row); entry["corrections"] = json.loads(entry["corrections"])
                entry["materials"] = [dict(m) for m in db.execute("SELECT id,name,mime,size,sha256 FROM evidence_materials WHERE submission_id=?", (entry["id"],))]
                submissions.append(entry)
            item["submissions"] = submissions
            item["history"] = [{**dict(row), "result": json.loads(row["result"])} for row in db.execute("SELECT * FROM review_events WHERE task_id=? ORDER BY id", (task_id,))]
            return item

    def submit(self, company_id, actor, task_id, revision, version_id, explanation, corrections, materials):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            latest = self.latest(company_id)
            if latest["id"] != version_id:
                raise ConflictError("企业数据已更新，请刷新并核对材料适用期间")
            if not task_id:
                task_id = f"RV-{uuid4().hex[:12].upper()}"
                db.execute("INSERT INTO review_tasks(id,company_id,version_id,period,kind,title,status,details,created_at,updated_at) VALUES(?,?,?,? ,?,?,'awaiting_material','{}',?,?)", (task_id, company_id, latest["id"], latest["period"], f"supplement_{uuid4().hex[:8]}", "企业主动补充说明", now(), now()))
                revision = 1
            row = db.execute("SELECT * FROM review_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError("审核任务不存在")
            if row["company_id"] != company_id:
                raise PermissionError("仅可补充本企业材料")
            if row["version_id"] != latest["id"] or row["revision"] != revision:
                raise ConflictError("数据版本或任务状态已变化，请刷新后提交")
            if row["status"] not in ("awaiting_material", "returned", "tracking"):
                raise ConflictError("当前任务不接受重复提交")
            if corrections:
                revise_payload(latest["payload"], corrections, latest["period"])
            submission_id = f"EV-{uuid4().hex[:12].upper()}"
            db.execute("INSERT INTO evidence_submissions VALUES(?,?,?,?,?,?)", (submission_id, task_id, actor, explanation, encoded(corrections), now()))
            for material in materials:
                db.execute("INSERT INTO evidence_materials VALUES(?,?,?,?,?,?,?)", (f"MT-{uuid4().hex[:12].upper()}", submission_id, material["name"], material["mime"], len(material["content"]), hashlib.sha256(material["content"]).hexdigest(), material["content"]))
            db.execute("UPDATE review_tasks SET status='pending_review',revision=revision+1,updated_at=? WHERE id=?", (now(), task_id))
            db.execute("INSERT INTO review_events(task_id,actor,action,comment,created_at,submission_id,result) VALUES(?,?,?,?,?,?,?)", (task_id, actor, "submit", explanation, now(), submission_id, "{}"))
        return self.task(task_id)

    def review(self, task_id, actor, revision, action, comment, before):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            task = self.task(task_id)
            if not task["is_current"] or task["revision"] != revision:
                raise ConflictError("任务数据或审核状态已变化，请刷新")
            if task["status"] != "pending_review" or not task["submissions"]:
                raise ConflictError("仅可审核企业已提交的材料")
            submission = task["submissions"][-1]
            outcome, status = None, "pending_review"
            if action == "approve_reasonable":
                if not submission["materials"]:
                    raise ValueError("核验通过需有至少一份佐证材料")
                outcome, status = "reasonable", "resolved"
            elif action == "approve_correction":
                if not submission["materials"] or not submission["corrections"]:
                    raise ValueError("更正通过需同时提供更正数据和佐证材料")
                latest = self.latest(task["company_id"])
                payload = revise_payload(latest["payload"], submission["corrections"], task["period"])
                self._insert_version(db, task["company_id"], payload, task["period"], "银行核验后的企业数据更正", keep_task=task_id)
                outcome, status = "corrected", "resolved"
            elif action == "return":
                status = "returned"
            elif action == "track":
                status = "tracking"
            else:
                raise ValueError("不支持的审核操作")
            db.execute("UPDATE review_tasks SET status=?,outcome=?,revision=revision+1,updated_at=? WHERE id=?", (status, outcome, now(), task_id))
            event = db.execute("INSERT INTO review_events(task_id,actor,action,comment,created_at,submission_id,result) VALUES(?,?,?,?,?,?,?)", (task_id, actor, action, comment, now(), submission["id"], encoded({"before": before})))
            return event.lastrowid

    def finish_review(self, event_id, after):
        with self.lock, self.connect() as db:
            result = json.loads(db.execute("SELECT result FROM review_events WHERE id=?", (event_id,)).fetchone()[0])
            result["after"] = after
            db.execute("UPDATE review_events SET result=? WHERE id=?", (encoded(result), event_id))

    def material(self, material_id):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT m.*,s.task_id,t.company_id FROM evidence_materials m JOIN evidence_submissions s ON s.id=m.submission_id JOIN review_tasks t ON t.id=s.task_id WHERE m.id=?", (material_id,)).fetchone()
            if not row:
                raise KeyError("材料不存在")
            return dict(row)


business_store = BusinessStore()
