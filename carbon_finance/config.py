from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
RANDOM_STATE = 42

# Equal channel coefficients preserve legacy scaling; these are demo, uncalibrated parameters.
NETWORK_RELATION_WEIGHTS = {"supply": 1.0, "energy": 1.0, "infra": 1.0}

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
    "transition_risk_weight": 1.0,
    "network_edge_scale": 0.35,
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
    "正常情景": {
        "shock": 0.0,
        "energy_cost_impact": 0.0,
        "cashflow_impact": 0.0,
        "progress_impact": 0.0,
        "probability_penalty": 0.0,
        "network_impact": 0.0,
        "driver": "基准经营环境",
        "change": 0.0,
        "description": "不施加额外外部冲击，用于形成授信测算基线。",
    },
    "天然气价格上涨30%": {
        "shock": 0.30,
        "energy_cost_impact": 0.18,
        "cashflow_impact": 0.45,
        "progress_impact": 0.08,
        "probability_penalty": 0.98,
        "network_impact": 0.90,
        "driver": "天然气价格",
        "change": 0.30,
        "description": "天然气成本上升，经能源成本和现金流覆盖传导至转型进度。",
    },
    "电价上涨20%": {
        "shock": 0.22,
        "energy_cost_impact": 0.23,
        "cashflow_impact": 0.36,
        "progress_impact": 0.06,
        "probability_penalty": 0.62,
        "network_impact": 0.65,
        "driver": "工业电价",
        "change": 0.20,
        "description": "工业电价上行，重点检验电炉、粉磨等高用电环节承压能力。",
    },
    "煤价上涨25%": {
        "shock": 0.27,
        "energy_cost_impact": 0.26,
        "cashflow_impact": 0.42,
        "progress_impact": 0.07,
        "probability_penalty": 0.68,
        "network_impact": 0.72,
        "driver": "动力煤价格",
        "change": 0.25,
        "description": "煤炭价格上行，重点检验钢铁、建材企业成本与技改现金流。",
    },
    "碳价上涨50%": {
        "shock": 0.24,
        "energy_cost_impact": 0.15,
        "cashflow_impact": 0.31,
        "progress_impact": 0.03,
        "probability_penalty": 0.58,
        "network_impact": 0.55,
        "driver": "碳配额价格",
        "change": 0.50,
        "description": "碳履约成本上升，检验高碳企业转型兑现和融资承受能力。",
    },
    "核心客户需求下降20%": {
        "shock": 0.35,
        "energy_cost_impact": 0.04,
        "cashflow_impact": 0.72,
        "progress_impact": 0.12,
        "probability_penalty": 0.82,
        "network_impact": 1.00,
        "driver": "核心客户需求",
        "change": -0.20,
        "description": "下游需求收缩，通过订单、现金流和园区供应链形成组合冲击。",
    },
}
