"""Stream actual model execution over a versioned, backend-managed snapshot."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from queue import Empty, Full, Queue
from threading import BoundedSemaphore, Event, Thread
from time import perf_counter
from uuid import uuid4

from carbon_finance.config import SCENARIOS
from carbon_finance.lmdi import decompose_lmdi
from carbon_finance.pipeline import CarbonFinancePipeline
from carbon_finance.transition import scenario_sensitivity
from services.analysis_service import _native

STAGES = (
    ("data", "后台数据读取与校验"),
    ("lmdi", "减排来源分解"),
    ("transition", "转型预测与异常识别"),
    ("network", "园区关联风险计算"),
    ("finance", "额度、定价与收益校验"),
    ("stress", "压力情景对照"),
    ("review", "核验任务与留痕"),
)
_slots = BoundedSemaphore(2)


def _ensure_table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS analysis_workflow_runs (
        id TEXT PRIMARY KEY, company_id TEXT NOT NULL, scenario TEXT NOT NULL,
        created_at TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL)""")


def list_runs(store, company_id, limit=10):
    with store.connect() as db:
        _ensure_table(db)
        rows = db.execute(
            "SELECT payload FROM analysis_workflow_runs WHERE company_id=? ORDER BY created_at DESC LIMIT ?",
            (company_id, max(1, min(limit, 20))),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def start_workflow(store, company_id, scenario):
    """Reserve capacity before returning HTTP 200; no client data can be imported."""
    if scenario not in SCENARIOS:
        raise ValueError("未知分析情景")
    latest = store.latest(company_id)
    if latest["payload"]["company"].get("evaluation_model") == "operating":
        raise ValueError("该主体使用运行风险模板，未适配转型融资工作流")
    if not _slots.acquire(blocking=False):
        raise RuntimeError("已有计算任务运行，请稍后重试")
    messages, cancelled = Queue(maxsize=64), Event()
    workflow_id = "CALC-" + uuid4().hex[:12].upper()

    def execute():
        events, timings = [], {}
        active, status = None, "running"
        started = perf_counter()
        created = datetime.now(timezone.utc).isoformat()

        def send(kind, **payload):
            event = _native({"type": kind, "workflow_id": workflow_id,
                             "sequence": len(events) + 1, "at": datetime.now(timezone.utc).isoformat(), **payload})
            events.append(event)
            while not cancelled.is_set():
                try:
                    messages.put(event, timeout=0.2)
                    return
                except Full:
                    continue
            raise InterruptedError("客户端已停止接收")

        def begin(stage):
            nonlocal active
            if cancelled.is_set():
                raise InterruptedError("计算已取消")
            active = stage
            timings[stage] = perf_counter()
            send("stage", stage=stage, status="running")

        def finish(stage, result):
            send("stage", stage=stage, status="completed", result=result,
                 duration_ms=round((perf_counter() - timings[stage]) * 1000, 2))

        try:
            send("started", company_id=company_id, scenario=scenario,
                 stages=[{"id": key, "name": name} for key, name in STAGES])
            begin("data")
            # All calculations below use this one immutable in-memory DB snapshot.
            with store.lock:
                data, versions = store.load_data()
                approved = store.approved_model_versions()
            version = next(v for v in versions if v["company_id"] == company_id)
            features = data["features"].loc[data["features"].company_id.eq(company_id)].copy()
            energy = data["energy"].loc[data["energy"].company_id.eq(company_id)].copy()
            if features.empty or energy.empty:
                raise ValueError("企业缺少转型指标或能耗数据，请由后台补齐")
            snapshot = {key: version[key] for key in ("id", "version", "period", "source", "created_at")}
            finish("data", {"data_version": snapshot, "company_name": version["payload"]["company"]["company_name"],
                            "energy_records": len(energy), "periods": int(energy.period.nunique()),
                            "company_count": len(data["companies"]), "network_relations": len(data["network"]),
                            "energy_preview": energy.sort_values(["period", "energy_type"]).tail(6).to_dict("records"),
                            "input_metrics": {key: float(features.iloc[0][key]) for key in
                                              ("project_progress", "fund_usage_match", "own_fund_arrival", "data_completeness")}})

            begin("lmdi")
            periods = sorted(energy.period.unique())
            selected_energy = energy.loc[energy.period.isin([periods[0], periods[-1]])]
            routes = [{k: v for k, v in row.items() if k != "company_id"}
                      for row in data.get("routes", []) if row["company_id"] == company_id]
            attribution = decompose_lmdi(selected_energy, routes)
            finish("lmdi", attribution)

            begin("transition")
            pipeline = CarbonFinancePipeline(data=data)
            pipeline.reviewed_company_ids = approved
            evaluations = None

            def report(stage, state, payload):
                nonlocal evaluations
                if state == "started":
                    begin(stage)
                    return
                if stage == "transition":
                    evaluations = payload
                    row = payload.set_index("company_id").loc[company_id]
                    explained_features = features.copy()
                    config = SCENARIOS[scenario]
                    shock = config["shock"]
                    if shock:
                        sensitivity = scenario_sensitivity(explained_features, config)
                        for field, factor, default, sign in (
                            ("energy_cost_ratio", "energy_cost_impact", .18, 1),
                            ("cashflow_coverage", "cashflow_impact", .45, -1),
                            ("project_progress", "progress_impact", .08, -1),
                        ):
                            explained_features[field] += sign * shock * sensitivity * config.get(factor, default)
                    explanation = pipeline.transition_engine.explain_probability(explained_features)
                    explanation["final_probability"] = float(row.p_target)
                    explanation["scenario_adjustment_pp"] = (float(row.p_target) - explanation["model_probability"]) * 100
                    finish(stage, {"p_target": row.p_target, "data_quality": row.data_quality,
                                   "anomaly_score": row.anomaly_score, "model_auc": pipeline.transition_engine.auc,
                                   "explanation": explanation})
                elif stage == "network":
                    row = payload["network"].set_index("company_id").loc[company_id]
                    finish(stage, {key: row[key] for key in ("own_risk", "first_order_risk", "second_order_risk", "network_risk")} |
                           {"paths": payload["paths"].get(company_id, [])[:3], "relation_count": len(payload["relations"])})
                elif stage == "finance":
                    row = payload.set_index("company_id").loc[company_id]
                    finish(stage, {key: row[key] for key in (
                        "base_limit", "transition_support", "network_deduction", "final_limit", "suggested_rate",
                        "raroc", "raroc_threshold", "raroc_passed", "warning_level", "action")})

            selected = pipeline.run(scenario, on_stage=report)
            begin("stress")
            normal = selected if scenario == "正常情景" else pipeline.run("正常情景")
            stress = selected if scenario == "天然气价格上涨30%" else pipeline.run("天然气价格上涨30%")
            comparison = {}
            for name, output in (("normal", normal), ("stress", stress)):
                row = output["companies"].set_index("company_id").loc[company_id]
                comparison[name] = {key: row[key] for key in ("p_target", "network_risk", "final_limit", "raroc")}
            finish("stress", {"normal_scenario": "正常情景", "stress_scenario": "天然气价格上涨30%", **comparison})

            begin("review")
            # Task creation concerns actual filed facts, not hypothetical stress inputs.
            observed = evaluations if scenario == "正常情景" else pipeline.evaluate_entities()
            store.reconcile_tasks(versions, observed)
            tasks = [t for t in store.tasks(company_id) if t["version_id"] == version["id"]]
            current = store.latest(company_id)
            finish("review", {"task_count": len(tasks), "tasks": [
                {key: task[key] for key in ("id", "title", "status")} for task in tasks],
                "snapshot_is_current": current["id"] == version["id"],
                "human_review_required": True, "data_version": snapshot})
            status = "completed"
            # Persist the actual events before announcing success to the client.
            record = {"workflow_id": workflow_id, "company_id": company_id, "scenario": scenario,
                      "created_at": created, "status": status, "data_version": snapshot,
                      "duration_ms": round((perf_counter() - started) * 1000, 2), "events": events.copy()}
            with store.connect() as db:
                _ensure_table(db)
                db.execute("INSERT INTO analysis_workflow_runs VALUES(?,?,?,?,?,?)",
                           (workflow_id, company_id, scenario, created, status, json.dumps(record, ensure_ascii=False, allow_nan=False)))
            send("completed", data_version=snapshot, duration_ms=record["duration_ms"],
                 snapshot_is_current=current["id"] == version["id"], human_review_required=True)
        except InterruptedError:
            status = "cancelled"
        except Exception as exc:
            status = "failed"
            logging.getLogger(__name__).exception("Analysis workflow %s failed", workflow_id)
            if not cancelled.is_set():
                try:
                    send("error", stage=active, status="failed", message=str(exc))
                except InterruptedError:
                    pass
        finally:
            if status != "completed":
                try:
                    record = {"workflow_id": workflow_id, "company_id": company_id, "scenario": scenario,
                              "created_at": created, "status": status, "events": events,
                              "duration_ms": round((perf_counter() - started) * 1000, 2)}
                    with store.connect() as db:
                        _ensure_table(db)
                        db.execute("INSERT OR IGNORE INTO analysis_workflow_runs VALUES(?,?,?,?,?,?)",
                                   (workflow_id, company_id, scenario, created, status, json.dumps(record, ensure_ascii=False, allow_nan=False)))
                except Exception:
                    logging.getLogger(__name__).exception("Could not persist workflow failure")
            _slots.release()
            while not cancelled.is_set():
                try:
                    messages.put(None, timeout=.2)
                    break
                except Full:
                    continue

    worker = Thread(target=execute, name=workflow_id, daemon=True)

    def stream():
        worker.start()
        try:
            while True:
                try:
                    message = messages.get(timeout=1)
                except Empty:
                    # Empty lines keep the connection live; these are not progress events.
                    yield "\n"
                    continue
                if message is None:
                    break
                yield json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n"
        finally:
            cancelled.set()

    return stream()
