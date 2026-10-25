from __future__ import annotations

import csv
import io
import json
import math
from collections import OrderedDict
from dataclasses import asdict, dataclass
from threading import RLock
from uuid import uuid4

from services.persistent_store import persistent_store


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 1000
MAX_COLUMNS = 80
MAX_DATASETS = 100
PREVIEW_ROWS = 8
ALLOWED_EXTENSIONS = {".csv", ".json"}
STRUCTURED_TABLES = (
    "companies", "energy_performance", "transition_projects",
    "fund_usage", "network_edges", "external_risks",
)


@dataclass(frozen=True)
class ImportedDataset:
    dataset_id: str
    filename: str
    columns: list[str]
    rows: list[dict]
    tables: dict[str, list[dict]]
    validation: dict


class DatasetStore:
    """Small process-local store for competition demos; uploaded bytes are not persisted."""

    def __init__(self) -> None:
        self._items: OrderedDict[str, ImportedDataset] = OrderedDict()
        self._lock = RLock()

    def import_file(self, filename: str, content: bytes) -> ImportedDataset:
        safe_name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        suffix = "." + safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValueError("仅支持 .csv 或 .json 文件")
        if not content:
            raise ValueError("上传文件为空")
        if len(content) > MAX_FILE_BYTES:
            raise ValueError("文件超过 10 MB 安全限制")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("文件必须使用 UTF-8 编码") from exc

        if suffix == ".csv":
            records = self._parse_csv(text)
            tables = {"companies": records}
        else:
            records, tables = self._parse_json(text)
            records = self._enrich_structured(records, tables)
        normalized, columns, validation = self._validate(records)
        table_counts = {name: len(rows) for name, rows in tables.items()}
        validation["source_tables"] = table_counts
        validation["structured"] = len(table_counts) > 1
        validation["missing_tables"] = [name for name in STRUCTURED_TABLES if name not in tables]
        item = ImportedDataset(
            dataset_id=f"DS-{uuid4().hex[:12].upper()}",
            filename=safe_name[:255],
            columns=columns,
            rows=normalized,
            tables=tables,
            validation=validation,
        )
        with self._lock:
            self._items[item.dataset_id] = item
            while len(self._items) > MAX_DATASETS:
                self._items.popitem(last=False)
        persistent_store.save_dataset(item.dataset_id, asdict(item), keep=MAX_DATASETS)
        return item

    def get(self, dataset_id: str) -> ImportedDataset:
        with self._lock:
            item = self._items.get(dataset_id)
        if item is None:
            saved = persistent_store.get_dataset(dataset_id)
            if saved is not None:
                item = ImportedDataset(**saved)
                with self._lock:
                    self._items[dataset_id] = item
        if item is None:
            raise KeyError("数据集不存在，请重新导入")
        return item

    @staticmethod
    def response(item: ImportedDataset) -> dict:
        industries = [str(row.get("industry")) for row in item.rows if row.get("industry")]
        return {
            "dataset_id": item.dataset_id,
            "filename": item.filename,
            "columns": item.columns,
            "rows": len(item.rows),
            "row_count": len(item.rows),
            "preview": item.rows[:PREVIEW_ROWS],
            "industry": industries[0] if industries else "",
            "source_tables": item.validation["source_tables"],
            "data_quality": item.validation["data_quality"],
            "validation": item.validation,
        }

    @staticmethod
    def _parse_csv(text: str) -> list[dict]:
        try:
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames:
                raise ValueError("CSV 缺少表头")
            if len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError("CSV 表头存在重复字段")
            return list(reader)
        except csv.Error as exc:
            raise ValueError(f"CSV 格式错误：{exc}") from exc

    @staticmethod
    def _parse_json(text: str) -> tuple[list[dict], dict[str, list[dict]]]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 格式错误：第 {exc.lineno} 行") from exc
        if isinstance(payload, dict) and isinstance(payload.get("companies"), list):
            tables = {}
            for name in STRUCTURED_TABLES:
                if name not in payload:
                    continue
                rows = payload[name]
                if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                    raise ValueError(f"结构化数据表 {name} 必须是对象数组")
                for row in rows:
                    if any(isinstance(value, (dict, list)) for value in row.values()):
                        raise ValueError(f"结构化数据表 {name} 不允许继续嵌套")
                tables[name] = rows
            return tables["companies"], tables
        if isinstance(payload, dict):
            payload = payload.get("rows", [payload])
        if not isinstance(payload, list):
            raise ValueError("JSON 顶层应为数组，或包含 companies/rows 数组")
        return payload, {"companies": payload}

    @staticmethod
    def _enrich_structured(companies: list[dict], tables: dict[str, list[dict]]) -> list[dict]:
        if len(tables) == 1:
            return companies
        enriched = [dict(row) for row in companies]
        company_map = {str(row.get("company_id")): row for row in enriched if row.get("company_id") is not None}

        energy_by_company: dict[str, list[dict]] = {}
        for row in tables.get("energy_performance", []):
            energy_by_company.setdefault(str(row.get("company_id")), []).append(row)
        for company_id, rows in energy_by_company.items():
            target = company_map.get(company_id)
            periods = sorted({str(row.get("period")) for row in rows if row.get("period") is not None})
            if target is None or len(periods) < 2:
                continue
            intensity = []
            for period in (periods[0], periods[-1]):
                period_rows = [row for row in rows if str(row.get("period")) == period]
                output = max(float(row.get("output", 0) or 0) for row in period_rows)
                emissions = sum(float(row.get("energy", 0) or 0) * float(row.get("emission_factor", 0) or 0) for row in period_rows)
                intensity.append(emissions / output if output > 0 else 0)
            if intensity[0] > 0:
                target.setdefault("intensity_trend", max(-.3, min(.4, (intensity[0] - intensity[1]) / intensity[0])))

        for row in tables.get("transition_projects", []):
            target = company_map.get(str(row.get("company_id")))
            if target is not None:
                target.setdefault("project_progress", row.get("project_progress", row.get("progress")))
                target.setdefault("milestone_delay_days", row.get("milestone_delay_days", row.get("delay_days")))
                target.setdefault("project_need", row.get("project_need", row.get("investment")))
        for row in tables.get("fund_usage", []):
            target = company_map.get(str(row.get("company_id")))
            if target is not None:
                target.setdefault("fund_usage_match", row.get("fund_usage_match", row.get("usage_match")))
                target.setdefault("own_fund_arrival", row.get("own_fund_arrival"))
        exposure: dict[str, float] = {}
        for row in tables.get("network_edges", []):
            weight = float(row.get("weight", 0) or 0)
            for endpoint in (row.get("source"), row.get("target")):
                exposure[str(endpoint)] = min(1.0, exposure.get(str(endpoint), 0.0) + weight * .5)
        for company_id, value in exposure.items():
            if company_id in company_map:
                company_map[company_id].setdefault("network_exposure", value)
        return enriched

    @staticmethod
    def _validate(records: list[dict]) -> tuple[list[dict], list[str], dict]:
        if not records:
            raise ValueError("文件没有数据行")
        if len(records) > MAX_ROWS:
            raise ValueError(f"数据行超过 {MAX_ROWS} 行安全限制")
        if any(not isinstance(row, dict) for row in records):
            raise ValueError("每一行必须是键值对象")
        columns = list(dict.fromkeys(str(key).strip() for row in records for key in row))
        if not columns or any(not column for column in columns):
            raise ValueError("字段名不能为空")
        if len(columns) > MAX_COLUMNS:
            raise ValueError(f"字段数超过 {MAX_COLUMNS} 列安全限制")

        normalized: list[dict] = []
        missing_cells = 0
        for row_index, row in enumerate(records, start=1):
            clean: dict = {}
            for column in columns:
                value = row.get(column)
                if isinstance(value, str):
                    value = value.strip()
                    if value == "":
                        value = None
                    else:
                        try:
                            value = float(value) if any(mark in value.lower() for mark in (".", "e")) else int(value)
                        except ValueError:
                            value = value[:500]
                if isinstance(value, (dict, list)):
                    raise ValueError(f"第 {row_index} 行字段 {column} 不允许嵌套结构")
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError(f"第 {row_index} 行字段 {column} 不是有限数值")
                if value is None:
                    missing_cells += 1
                clean[column] = value
            normalized.append(clean)

        recommended = {"company_id", "company_name", "base_limit", "project_need"}
        missing_recommended = sorted(recommended - set(columns))
        warnings = []
        if missing_recommended:
            warnings.append("缺少推荐字段：" + "、".join(missing_recommended))
        if missing_cells:
            warnings.append(f"发现 {missing_cells} 个空值，将使用审慎默认值计算")
        validation = {
            "status": "warning" if warnings else "passed",
            "valid": True,
            "warnings": warnings,
            "data_quality": 1 - missing_cells / max(1, len(normalized) * len(columns)),
            "limits": {"max_file_mb": 10, "max_rows": MAX_ROWS, "max_columns": MAX_COLUMNS},
        }
        return normalized, columns, validation


dataset_store = DatasetStore()
