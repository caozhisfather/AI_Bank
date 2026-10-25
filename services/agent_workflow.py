from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4


@dataclass
class AgentStep:
    id: str
    name: str
    role: str
    status: str
    conclusion: str
    evidence: list[str]
    action: str
    duration_ms: int


class AgentWorkflow:
    """Deterministic, auditable agent orchestration over model outputs."""

    def run(self, analysis: dict) -> dict:
        company = analysis["company"]
        project = analysis["project"]
        lmdi = analysis["lmdi"]
        paths = analysis["risk_paths"]
        steps = [
            self._timed("data-agent", "数据核验 Agent", "核验数据完整性、异常组合与资金用途", lambda: self._data(company, project)),
            self._timed("transition-agent", "转型识别 Agent", "解释历史减排并评估未来目标兑现", lambda: self._transition(company, lmdi, analysis["shap"])),
            self._timed("network-agent", "园区风险 Agent", "分析自身、一阶和二阶风险传播", lambda: self._network(company, paths)),
            self._timed("finance-agent", "融资决策 Agent", "在风险收益约束下形成融资建议", lambda: self._finance(company)),
            self._timed("compliance-agent", "合规复核 Agent", "检查模型边界并形成转人工结论", lambda: self._compliance(company)),
        ]
        review_required = True
        overall = "需人工复核" if any(step.status in {"warning", "blocked"} for step in steps) else "建议进入人工审批"
        return {
            "workflow_id": f"WF-{uuid4().hex[:10].upper()}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "company_id": company["company_id"],
            "company_name": company["company_name"],
            "scenario": analysis["scenario"],
            "status": "completed",
            "overall_conclusion": overall,
            "human_review_required": review_required,
            "steps": [asdict(step) for step in steps],
            "audit": {
                "engine": "deterministic-rule-agents-v1",
                "model_outputs_used": ["LMDI", "LightGBM/SHAP", "IsolationForest", "NetworkRisk", "RAROC"],
                "boundary": "Agent 仅生成辅助建议，不执行自动批贷、合同修改或漂绿认定。",
            },
        }

    def _timed(self, agent_id: str, name: str, role: str, task) -> AgentStep:
        started = perf_counter()
        payload = task()
        return AgentStep(agent_id, name, role, duration_ms=max(1, int((perf_counter() - started) * 1000)), **payload)

    @staticmethod
    def _data(company: dict, project: dict) -> dict:
        anomaly = company.get("effective_anomaly_score", company["anomaly_score"])
        quality = company["data_quality"]
        status = "warning" if anomaly >= 0.40 or quality < 0.80 else "passed"
        return {
            "status": status,
            "conclusion": "数据存在需核验项" if status == "warning" else "数据证据链基本可信",
            "evidence": [f"数据可信度 {quality:.1%}", f"异常分数 {anomaly:.1%}", f"资金用途一致率 {project['fund_usage_match']:.1%}"],
            "action": "抽查发票、设备合同及付款路径" if status == "warning" else "进入转型真实性识别",
        }

    @staticmethod
    def _transition(company: dict, lmdi: dict, shap: list[dict]) -> dict:
        probability = company["p_target"]
        real_reduction = lmdi["efficiency"] + lmdi["energy_structure"] < 0
        status = "passed" if probability >= 0.70 and real_reduction else "warning"
        drivers = "、".join(item["label"] for item in shap[:3])
        return {
            "status": status,
            "conclusion": "转型路径具备较高兑现可能" if status == "passed" else "转型兑现能力需持续观察",
            "evidence": [f"12个月达标概率 {probability:.1%}", f"能效效应 {lmdi['efficiency']:+.2f}", f"主要驱动：{drivers}"],
            "action": "将达标概率传入园区风险节点" if status == "passed" else "缩短观察期并补充里程碑材料",
        }

    @staticmethod
    def _network(company: dict, paths: list[dict]) -> dict:
        risk = company["network_risk"]
        status = "warning" if risk >= 0.28 else "passed"
        path_text = paths[0]["path"] if paths else "无显著传播路径"
        return {
            "status": status,
            "conclusion": "园区关联风险偏高" if status == "warning" else "园区关联风险处于可观察范围",
            "evidence": [f"综合关联风险 {risk:.1%}", f"一阶风险 {company['first_order_risk']:.1%}", f"首要路径 {path_text}"],
            "action": "提高网络风险扣减并人工核查路径" if status == "warning" else "进入融资额度与定价计算",
        }

    @staticmethod
    def _finance(company: dict) -> dict:
        passed = bool(company["raroc_passed"])
        return {
            "status": "passed" if passed else "blocked",
            "conclusion": "融资建议满足演示风险收益底线" if passed else "融资方案未通过 RAROC 底线",
            "evidence": [f"建议额度 {company['final_limit']:.0f}万元", f"建议利率 {company['suggested_rate']:.2%}", f"RAROC {company['raroc']:.1%}"],
            "action": company["action"] if passed else "调整额度或定价后重新计算",
        }

    @staticmethod
    def _compliance(company: dict) -> dict:
        high_alert = str(company["warning_level"]).startswith("红色")
        return {
            "status": "warning" if high_alert else "passed",
            "conclusion": "触发加强型人工复核" if high_alert else "模型表述边界检查通过",
            "evidence": [f"当前预警 {company['warning_level']}", "算法结果定位为辅助决策", "异常信号不构成漂绿认定"],
            "action": "提交有权审批人复核，Agent 不自动执行授信动作",
        }
