from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
RANDOM_STATE = 42

DEMO_PARAMS = {
    "support_ratio": 0.80,
    "network_risk_factor": 0.20,
    "network_deduction_cap": 0.15,
    "propagation_decay": 0.55,
    "base_rate": 0.038,
    "credit_premium": 0.001,
    "max_transition_discount": 0.0015,
    "network_premium_factor": 0.006,
    "raroc_threshold": 0.085,
    "operating_cost_rate": 0.002,
    "risk_capital_rate": 0.12,
    "loss_given_default": 0.45,
}

FEATURE_COLUMNS = [
    "lmdi_efficiency_share",
    "lmdi_energy_share",
    "intensity_trend",
    "project_progress",
    "milestone_delay_days",
    "fund_usage_match",
    "own_fund_arrival",
    "cashflow_coverage",
    "energy_cost_ratio",
    "data_completeness",
]

FEATURE_LABELS = {
    "lmdi_efficiency_share": "能效减排贡献",
    "lmdi_energy_share": "能源结构减排贡献",
    "intensity_trend": "碳强度改善趋势",
    "project_progress": "技改项目进度",
    "milestone_delay_days": "里程碑延迟天数",
    "fund_usage_match": "资金用途一致率",
    "own_fund_arrival": "自有资金到位率",
    "cashflow_coverage": "经营现金流覆盖",
    "energy_cost_ratio": "能源成本占比",
    "data_completeness": "数据完整度",
}

SCENARIOS = {
    "正常情景": {"shock": 0.0, "gas_price_change": 0.0},
    "天然气价格上涨30%": {"shock": 0.30, "gas_price_change": 0.30},
}
