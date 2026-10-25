from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict
from uuid import uuid4

from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from carbon_finance.config import SCENARIOS
from carbon_finance.finance import make_financing_decision
from services.dataset_service import ImportedDataset


def _number(row: dict, key: str, default: float, low: float = 0.0, high: float | None = None) -> float:
    try:
        value = float(row.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(value, high)) if high is not None else max(low, value)


@tool
def validate_company_data(rows_json: str) -> dict:
    """Validate imported company rows and report data quality for risk analysis."""
    rows = json.loads(rows_json)
    required = ("company_id", "company_name", "base_limit", "project_need")
    complete = sum(value not in (None, "") for row in rows for value in row.values())
    total = max(1, sum(len(row) for row in rows))
    missing = sorted({key for key in required if any(row.get(key) in (None, "") for row in rows)})
    return {"data_quality": complete / total, "missing_required": missing, "row_count": len(rows)}


@tool
def calculate_transition_scores(rows_json: str, scenario_shock: float = 0.0) -> list[dict]:
    """Calculate deterministic transition target probabilities from project and carbon indicators."""
    rows = json.loads(rows_json)
    results = []
    for index, row in enumerate(rows):
        progress = _number(row, "project_progress", 0.70, high=1.0)
        usage = _number(row, "fund_usage_match", 0.85, high=1.0)
        completeness = _number(row, "data_completeness", 0.90, high=1.0)
        improvement = _number(row, "intensity_trend", 0.08, low=-1.0, high=1.0)
        sensitivity = _number(row, "shock_sensitivity", 0.30, high=1.0)
        probability = 0.18 + 0.30 * progress + 0.20 * usage + 0.16 * completeness + 0.55 * improvement
        probability -= scenario_shock * sensitivity * 0.42
        results.append({
            "company_id": str(row.get("company_id") or f"ROW-{index + 1}"),
            "p_target": max(0.05, min(probability, 0.98)),
            "project_progress": progress,
        })
    return results


@tool
def calculate_park_network_risk(rows_json: str, transition_json: str, propagation_decay: float = 0.55) -> list[dict]:
    """Calculate own, first-order and second-order park risk using the two-stage propagation model."""
    rows = json.loads(rows_json)
    transition = json.loads(transition_json)
    average_own = sum(1 - item["p_target"] for item in transition) / max(1, len(transition))
    results = []
    for row, score in zip(rows, transition):
        own = 1 - score["p_target"]
        exposure = _number(row, "network_exposure", 0.25, high=1.0)
        first = propagation_decay * exposure * average_own
        second = propagation_decay**2 * exposure * average_own * 0.5
        results.append({
            "company_id": score["company_id"],
            "own_risk": own,
            "first_order_risk": first,
            "second_order_risk": second,
            "network_risk": min(1.0, own + first + second),
        })
    return results


@tool
def calculate_financing_plan(rows_json: str, transition_json: str, network_json: str, params_json: str = "{}") -> list[dict]:
    """Run the existing quota, pricing and RAROC financing algorithm for each company."""
    rows = json.loads(rows_json)
    transition = json.loads(transition_json)
    network = json.loads(network_json)
    params = json.loads(params_json)
    allowed_params = {
        "support_ratio", "network_risk_factor", "network_deduction_cap", "base_rate",
        "credit_premium", "max_transition_discount", "network_premium_factor", "raroc_threshold",
    }
    clean_params = {key: float(value) for key, value in params.items() if key in allowed_params}
    if any(not math.isfinite(value) or value < 0 or value > 2 for value in clean_params.values()):
        raise ValueError("算法参数必须是 0 到 2 之间的有限数值")
    results = []
    for row, score, risk in zip(rows, transition, network):
        decision = make_financing_decision(
            base_limit=_number(row, "base_limit", 1000.0),
            project_need=_number(row, "project_need", 300.0),
            p_target=score["p_target"],
            data_quality=_number(row, "data_completeness", 0.90, high=1.0),
            network_risk=risk["network_risk"],
            anomaly_score=_number(row, "anomaly_score", 0.15, high=1.0),
            params=clean_params,
        )
        results.append({"company_id": score["company_id"], **decision})
    return results


@tool
def review_compliance(finance_json: str) -> dict:
    """Apply compliance guardrails and require human approval for every financing recommendation."""
    plans = json.loads(finance_json)
    blocked = sum(not item["raroc_passed"] or str(item["warning_level"]).startswith("红色") for item in plans)
    return {
        "human_review_required": True,
        "blocked_count": blocked,
        "boundary": "Agent 仅生成辅助建议，不执行自动批贷、合同修改或漂绿认定。",
    }


class WorkflowState(TypedDict, total=False):
    rows: list[dict]
    options: dict
    results: dict[str, Any]
    steps: Annotated[list[dict], lambda left, right: left + right]


def _agent_enabled(state: WorkflowState, agent_id: str) -> bool:
    enabled = state["options"].get("enabled_agents")
    return not enabled or agent_id in enabled


def _step(agent_id: str, name: str, role: str, status: str, conclusion: str, evidence: list[str]) -> dict:
    return {"id": agent_id, "name": name, "role": role, "status": status, "conclusion": conclusion,
            "evidence": evidence, "action": "提交下一专业 Agent 处理", "duration_ms": 1}


def _data_node(state: WorkflowState) -> dict:
    result = validate_company_data.invoke({"rows_json": json.dumps(state["rows"], ensure_ascii=False)})
    status = "warning" if result["missing_required"] else "passed"
    step = _step(
        "data-agent", "数据核验 Agent", "核验字段完整性、数据质量和异常输入", status,
        "数据可进入审慎计算" if status == "passed" else "部分字段将采用审慎默认值",
        [f"数据质量 {result['data_quality']:.1%}", f"企业记录 {result['row_count']} 条"],
    )
    return {"results": {**state.get("results", {}), "validation": result}, "steps": [step] if _agent_enabled(state, "data") else []}


def _transition_node(state: WorkflowState) -> dict:
    scenario_name = state["options"].get("scenario", "正常情景")
    if scenario_name not in SCENARIOS:
        raise ValueError(f"未知情景：{scenario_name}")
    shock = float(SCENARIOS[scenario_name]["shock"])
    result = calculate_transition_scores.invoke({"rows_json": json.dumps(state["rows"], ensure_ascii=False), "scenario_shock": shock})
    avg = sum(item["p_target"] for item in result) / len(result)
    step = _step(
        "transition-agent", "转型识别 Agent", "计算转型达标概率与情景敏感性", "passed" if avg >= 0.65 else "warning",
        "已完成转型概率评估", [f"平均达标概率 {avg:.1%}", f"情景冲击 {shock:.0%}"],
    )
    return {"results": {**state["results"], "transition": result}, "steps": [step] if _agent_enabled(state, "transition") else []}


def _network_node(state: WorkflowState) -> dict:
    decay = float(state["options"].get("propagation_decay", 0.55))
    result = calculate_park_network_risk.invoke({
        "rows_json": json.dumps(state["rows"], ensure_ascii=False),
        "transition_json": json.dumps(state["results"]["transition"]), "propagation_decay": decay,
    })
    avg = sum(item["network_risk"] for item in result) / len(result)
    step = _step(
        "network-agent", "园区风险 Agent", "执行两阶关联风险传播", "warning" if avg >= 0.32 else "passed",
        "已完成园区网络风险传导", [f"平均网络风险 {avg:.1%}", f"传播衰减 {decay:.2f}"],
    )
    return {"results": {**state["results"], "network": result}, "steps": [step] if _agent_enabled(state, "park_risk") else []}


def _finance_node(state: WorkflowState) -> dict:
    params = state["options"].get("algorithm_params", {})
    if "support_ratio" in state["options"]:
        params = {**params, "support_ratio": state["options"]["support_ratio"]}
    result = calculate_financing_plan.invoke({
        "rows_json": json.dumps(state["rows"], ensure_ascii=False),
        "transition_json": json.dumps(state["results"]["transition"]),
        "network_json": json.dumps(state["results"]["network"]), "params_json": json.dumps(params),
    })
    blocked = sum(not item["raroc_passed"] for item in result)
    step = _step(
        "finance-agent", "融资决策 Agent", "执行额度、定价与 RAROC 算法", "blocked" if blocked else "passed",
        "已生成辅助融资建议", [f"方案数量 {len(result)}", f"未过 RAROC 底线 {blocked} 家"],
    )
    return {"results": {**state["results"], "financing": result}, "steps": [step] if _agent_enabled(state, "finance") else []}


def _compliance_node(state: WorkflowState) -> dict:
    result = review_compliance.invoke({"finance_json": json.dumps(state["results"]["financing"], ensure_ascii=False)})
    step = _step(
        "compliance-agent", "合规复核 Agent", "执行模型边界检查并转人工审批", "warning" if result["blocked_count"] else "passed",
        "所有建议均需人工审批", [result["boundary"], f"重点复核 {result['blocked_count']} 家"],
    )
    return {"results": {**state["results"], "compliance": result}, "steps": [step] if _agent_enabled(state, "compliance") else []}


def _build_graph():
    builder = StateGraph(WorkflowState)
    builder.add_node("data_validation", _data_node)
    builder.add_node("transition_analysis", _transition_node)
    builder.add_node("park_network_risk", _network_node)
    builder.add_node("financing_decision", _finance_node)
    builder.add_node("compliance_review", _compliance_node)
    builder.add_edge(START, "data_validation")
    builder.add_edge("data_validation", "transition_analysis")
    builder.add_edge("transition_analysis", "park_network_risk")
    builder.add_edge("park_network_risk", "financing_decision")
    builder.add_edge("financing_decision", "compliance_review")
    builder.add_edge("compliance_review", END)
    return builder.compile()


WORKFLOW_GRAPH = _build_graph()


def _deepagent_supervision(options: dict, results: dict) -> dict:
    requested = options.get("agent_mode") in {"deepagent", "deepagents", "online"}
    model = os.getenv("DEEPAGENT_MODEL")
    has_key = bool(os.getenv("OPENAI_API_KEY"))
    if not requested:
        return {"mode": "offline_deterministic", "enabled": False, "reason": "未选择 DeepAgents 在线监督"}
    if not model or not has_key:
        return {"mode": "offline_deterministic", "enabled": False, "reason": "未配置 DEEPAGENT_MODEL 或 OPENAI_API_KEY"}
    try:
        from deepagents import create_deep_agent

        supervisor = create_deep_agent(
            model=model,
            tools=[validate_company_data, calculate_transition_scores, calculate_park_network_risk,
                   calculate_financing_plan, review_compliance],
            system_prompt="你是转型金融合规监督 Agent，只复核证据，不得自动批贷或改变算法结果。",
            name="transition-finance-supervisor",
        )
        response = supervisor.invoke({"messages": [{"role": "user", "content":
            "复核以下确定性算法摘要，只指出风险与人工复核项：" + json.dumps(results, ensure_ascii=False)[:12000]}]})
        messages = response.get("messages", [])
        content = getattr(messages[-1], "content", "") if messages else ""
        return {"mode": "deepagents_supervised", "enabled": True, "model": model, "review": content}
    except Exception as exc:  # External model failures must never break the offline competition flow.
        return {"mode": "offline_deterministic", "enabled": False, "reason": f"DeepAgents 监督失败，已降级：{type(exc).__name__}"}


def run_imported_workflow(dataset: ImportedDataset, options: dict) -> dict:
    final = WORKFLOW_GRAPH.invoke({"rows": dataset.rows, "options": options, "results": {}, "steps": []})
    results = final["results"]
    supervision = _deepagent_supervision(options, results)
    workflow = {
        "workflow_id": f"WF-{uuid4().hex[:10].upper()}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_id": dataset.dataset_id,
        "status": "completed",
        "overall_conclusion": "建议进入人工审批",
        "human_review_required": True,
        "steps": final["steps"],
        "orchestration": {"engine": "langgraph", "graph": ["data_validation", "transition_analysis", "park_network_risk", "financing_decision", "compliance_review"],
                          "enabled_agents": options.get("enabled_agents") or ["data", "transition", "park_risk", "finance", "compliance"]},
        "supervision": supervision,
        "audit": {"tools": [tool_.name for tool_ in (validate_company_data, calculate_transition_scores, calculate_park_network_risk, calculate_financing_plan, review_compliance)],
                  "boundary": results["compliance"]["boundary"]},
    }
    analysis = {
        "dataset": {"filename": dataset.filename, "rows": len(dataset.rows)},
        "scenario": options.get("scenario", "正常情景"),
        "industry": options.get("industry", "自动识别"),
        **results,
    }
    return {"workflow": workflow, "analysis": analysis, "agent_mode": supervision["mode"]}
