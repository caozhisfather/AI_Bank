from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import DEMO_PARAMS


@dataclass
class FinancingDecision:
    base_limit: float
    transition_support: float
    network_deduction: float
    final_limit: float
    suggested_rate: float
    initial_rate: float
    loan_income_before_adjustment: float
    expected_loss: float
    operating_cost: float
    risk_capital: float
    raroc_before_adjustment: float
    raroc_threshold: float
    raroc: float
    raroc_passed: bool
    warning_level: str
    action: str


def make_financing_decision(
    base_limit: float,
    project_need: float,
    p_target: float,
    data_quality: float,
    network_risk: float,
    anomaly_score: float,
    params: dict[str, float] | None = None,
) -> dict[str, float | bool | str]:
    cfg = {**DEMO_PARAMS, **(params or {})}
    support = project_need * cfg["support_ratio"] * p_target * data_quality
    if cfg.get('round_intermediates', False):
        support = float(round(support))
    deduction_rate = min(
        cfg["network_deduction_cap"], cfg["network_risk_factor"] * network_risk
    )
    deduction = (base_limit + support) * deduction_rate
    if cfg.get('round_intermediates', False):
        deduction = float(round(deduction))
    final_limit = max(0.0, base_limit + support - deduction)

    discount = cfg["max_transition_discount"] * p_target * data_quality
    network_premium = cfg["network_premium_factor"] * network_risk
    rate = cfg["base_rate"] + cfg["credit_premium"] + network_premium - discount
    pd_estimate = min(0.18, cfg.get('pd_intercept',0.012) + 0.055 * network_risk + 0.025 * (1 - p_target))
    expected_loss = final_limit * pd_estimate * cfg["loss_given_default"]
    operating_cost = final_limit * cfg["operating_cost_rate"]
    risk_capital = max(final_limit * cfg["risk_capital_rate"], 1e-9)
    initial_rate = rate
    loan_income_before_adjustment = final_limit * initial_rate
    raroc_before_adjustment = (
        loan_income_before_adjustment - expected_loss - operating_cost
    ) / risk_capital
    raroc = raroc_before_adjustment
    if raroc < cfg["raroc_threshold"]:
        rate += (cfg["raroc_threshold"] - raroc) * cfg["risk_capital_rate"]
        raroc = cfg["raroc_threshold"]

    if anomaly_score >= 0.65 or network_risk >= 0.55:
        level, action = "红色-干预", "建议暂停新增提款并启动人工授信复核"
    elif anomaly_score >= 0.40 or network_risk >= cfg.get('attention_risk_threshold',0.32):
        level, action = "橙色-关注", "建议暂停新增绩效优惠，3-5个工作日内人工核查"
    elif network_risk >= 0.20 or p_target < 0.65:
        level, action = "黄色-观察", "建议缩短观察期并补充项目进度说明"
    else:
        level, action = "绿色-正常", "建议维持方案并按月监测里程碑"

    return asdict(
        FinancingDecision(
            base_limit=base_limit,
            transition_support=support,
            network_deduction=deduction,
            final_limit=final_limit,
            suggested_rate=rate,
            initial_rate=initial_rate,
            loan_income_before_adjustment=loan_income_before_adjustment,
            expected_loss=expected_loss,
            operating_cost=operating_cost,
            risk_capital=risk_capital,
            raroc_before_adjustment=raroc_before_adjustment,
            raroc_threshold=cfg["raroc_threshold"],
            raroc=raroc,
            raroc_passed=raroc >= cfg["raroc_threshold"],
            warning_level=level,
            action=action,
        )
    )
