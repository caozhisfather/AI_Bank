from __future__ import annotations

import pandas as pd

from .config import DEMO_PARAMS, SCENARIOS
from .data import load_demo_data
from .finance import make_financing_decision
from .lmdi import decompose_lmdi
from .network import propagate_risk
from .transition import TransitionEngine


class CarbonFinancePipeline:
    def __init__(self) -> None:
        self.data = load_demo_data()
        self.transition_engine = TransitionEngine().fit(self.data["training"])

    def run(self, scenario_name: str = "正常情景") -> dict:
        if scenario_name not in SCENARIOS:
            raise ValueError(f"未知情景：{scenario_name}")
        scenario = SCENARIOS[scenario_name]
        evaluations = self.transition_engine.evaluate(
            self.data["features"], shock=scenario["shock"]
        )
        nodes = self.data["companies"][["company_id", "company_name"]].merge(
            evaluations[["company_id", "p_target"]], on="company_id"
        )
        sensitivity = self.data["features"].set_index("company_id")["shock_sensitivity"]
        nodes["initial_risk"] = (
            1 - nodes["p_target"]
            + scenario["shock"] * nodes["company_id"].map(sensitivity) * 0.42
        ).clip(0, 1)
        network, paths = propagate_risk(
            nodes,
            self.data["network"],
            decay=DEMO_PARAMS["propagation_decay"],
        )

        companies = self.data["companies"].merge(evaluations, on=["company_id", "company_name"])
        companies = companies.merge(network, on=["company_id", "company_name"])
        decisions = []
        for row in companies.itertuples():
            decision = make_financing_decision(
                base_limit=row.base_limit,
                project_need=row.project_need,
                p_target=row.p_target,
                data_quality=row.data_quality,
                network_risk=row.network_risk,
                anomaly_score=row.anomaly_score,
            )
            decision_fields = {
                key: value for key, value in decision.items() if key != "base_limit"
            }
            decisions.append({"company_id": row.company_id, **decision_fields})
        companies = companies.merge(pd.DataFrame(decisions), on="company_id")
        return {
            "scenario": scenario_name,
            "companies": companies,
            "network": network,
            "paths": paths,
            "model_auc": self.transition_engine.auc,
        }

    def company_detail(self, company_id: str, scenario_name: str = "正常情景") -> dict:
        results = self.run(scenario_name)
        row = results["companies"].loc[
            results["companies"]["company_id"] == company_id
        ]
        if row.empty:
            raise KeyError(f"企业不存在：{company_id}")
        feature_row = self.data["features"].loc[
            self.data["features"]["company_id"] == company_id
        ].copy()
        shock = SCENARIOS[scenario_name]["shock"]
        if shock:
            sensitivity = feature_row["shock_sensitivity"]
            feature_row["energy_cost_ratio"] += shock * sensitivity * 0.18
            feature_row["cashflow_coverage"] -= shock * sensitivity * 0.45
            feature_row["project_progress"] -= shock * sensitivity * 0.08
        energy = self.data["energy"].loc[
            self.data["energy"]["company_id"] == company_id
        ]
        return {
            **results,
            "company": row.iloc[0].to_dict(),
            "lmdi": decompose_lmdi(energy),
            "shap": self.transition_engine.explain(feature_row),
            "top_paths": results["paths"][company_id],
        }
