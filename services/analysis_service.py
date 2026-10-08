from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from carbon_finance.config import SCENARIOS
from carbon_finance.pipeline import CarbonFinancePipeline


def _native(value):
    if isinstance(value, dict):
        return {key: _native(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_native(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    return value


def _records(frame: pd.DataFrame) -> list[dict]:
    cleaned = frame.replace({np.nan: None})
    return _native(cleaned.to_dict(orient="records"))


class AnalysisService:
    def __init__(self) -> None:
        self.pipeline = CarbonFinancePipeline()

    def metadata(self) -> dict:
        companies = self.pipeline.data["companies"]
        return {
            "companies": _records(companies[["company_id", "company_name", "industry"]]),
            "scenarios": list(SCENARIOS),
            "model_auc": self.pipeline.transition_engine.auc,
            "disclaimer": "模拟数据与演示参数，仅用于竞赛算法原型验证，不构成正式授信结论。",
        }

    def dashboard(self, scenario: str) -> dict:
        result = self.pipeline.run(scenario)
        companies = result["companies"]
        columns = [
            "company_id", "company_name", "industry", "base_limit", "project_need",
            "p_target", "transition_score", "data_quality", "anomaly_score",
            "own_risk", "first_order_risk", "second_order_risk", "network_risk",
            "transition_support", "network_deduction", "final_limit", "suggested_rate",
            "raroc", "warning_level", "action",
        ]
        return {
            "scenario": scenario,
            "summary": {
                "company_count": len(companies),
                "base_exposure": float(companies["base_limit"].sum()),
                "project_need": float(companies["project_need"].sum()),
                "alerts": int(companies["warning_level"].str.contains("关注|干预").sum()),
            },
            "companies": _records(companies[columns]),
        }

    def company_analysis(self, company_id: str, scenario: str) -> dict:
        detail = self.pipeline.company_detail(company_id, scenario)
        normal = self.pipeline.company_detail(company_id, "正常情景")
        stress = self.pipeline.company_detail(company_id, "天然气价格上涨30%")
        feature = self.pipeline.data["features"].loc[
            self.pipeline.data["features"]["company_id"] == company_id
        ].iloc[0]
        company = detail["company"]
        return _native({
            "scenario": scenario,
            "company": company,
            "project": {
                "name": company["project_name"],
                "progress": feature["project_progress"],
                "own_fund_arrival": feature["own_fund_arrival"],
                "fund_usage_match": feature["fund_usage_match"],
                "milestone_delay_days": feature["milestone_delay_days"],
            },
            "lmdi": detail["lmdi"],
            "shap": _records(detail["shap"]),
            "risk_paths": detail["top_paths"],
            "network": _records(detail["network"]),
            "comparison": {
                "normal": normal["company"],
                "stress": stress["company"],
            },
            "model_auc": detail["model_auc"],
        })


@lru_cache(maxsize=1)
def get_analysis_service() -> AnalysisService:
    return AnalysisService()
