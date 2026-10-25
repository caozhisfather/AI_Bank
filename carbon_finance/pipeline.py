from __future__ import annotations

import json
import numpy as np
import pandas as pd

from .config import DEMO_PARAMS, SCENARIOS, NETWORK_RELATION_WEIGHTS
from .data import load_demo_data
from .finance import make_financing_decision
from .lmdi import decompose_lmdi
from .network import prepare_network, propagate_risk, support_risk_nodes
from .mitigation import apply_mitigation_profiles
from .transition import TransitionEngine, scenario_sensitivity


class CarbonFinancePipeline:
    def __init__(self, data: dict | None = None) -> None:
        self.data = data if data is not None else load_demo_data()
        self.reviewed_company_ids: set[str] = set()
        self.transition_engine = TransitionEngine().fit(self.data["training"])

    def evaluate_entities(self, scenario=None):
        scenario = scenario or SCENARIOS['正常情景']
        features = self.data['features']
        eligible = features.get('evaluation_model', pd.Series('transition', index=features.index)).eq('transition')
        result = self.transition_engine.evaluate(features.loc[eligible], shock=scenario['shock'], scenario=scenario)
        other = features.loc[~eligible, ['company_id', 'company_name']].copy()
        if not other.empty:
            other['p_target'] = np.nan
            other['transition_score'] = np.nan
            other['anomaly_score'] = 0.
            other['data_quality'] = features.loc[~eligible, 'data_completeness'].to_numpy()
            result = pd.concat([result, other], ignore_index=True)
        return result

    def run(self, scenario_name: str = "正常情景") -> dict:
        if scenario_name not in SCENARIOS:
            raise ValueError(f"未知情景：{scenario_name}")
        scenario = SCENARIOS[scenario_name]
        evaluations = self.evaluate_entities(scenario)
        evaluations["raw_anomaly_score"] = evaluations["anomaly_score"]
        evaluations["raw_data_quality"] = evaluations["data_quality"]
        evaluations["effective_anomaly_score"] = evaluations["anomaly_score"]
        evaluations["anomaly_reviewed"] = False
        # A decision covers one actual data version, not simulated future shocks.
        if scenario_name == "正常情景":
            reviewed = evaluations["company_id"].isin(self.reviewed_company_ids)
            completeness = self.data["features"].set_index("company_id")["data_completeness"]
            evaluations.loc[reviewed, "data_quality"] = evaluations.loc[reviewed, "company_id"].map(completeness).clip(0.55, 1)
            evaluations.loc[reviewed, "effective_anomaly_score"] = 0.0
            evaluations.loc[reviewed, "anomaly_reviewed"] = True
        nodes = self.data["companies"][["company_id", "company_name"]].merge(
            evaluations[["company_id", "p_target"]], on="company_id"
        )
        sensitivity = self.data["features"].set_index("company_id")["shock_sensitivity"]
        direct_sensitivity = self.data['features'].set_index('company_id').get('direct_shock_sensitivity', sensitivity).fillna(sensitivity)
        nodes["initial_risk"] = (
            DEMO_PARAMS["transition_risk_weight"] * (1 - nodes["p_target"])
            + scenario["shock"] * nodes["company_id"].map(direct_sensitivity) * scenario.get("network_impact", 0.42)
        ).clip(0, 1)
        operating = self.data.get('operation_profiles', pd.DataFrame())
        if not operating.empty:
            profiles = operating.set_index('company_id')
            modeled = self.data['features'].set_index('company_id').evaluation_model
            mask = nodes.company_id.map(modeled).eq('operating')
            sensitivity = scenario_sensitivity(profiles.assign(shock_sensitivity=0), scenario)
            own = (profiles.baseline_risk + scenario['shock'] * sensitivity).clip(0, 1)
            nodes.loc[mask, 'initial_risk'] = nodes.loc[mask, 'company_id'].map(own)
        support = support_risk_nodes(self.data.get("support_nodes"), set(nodes.company_id))
        if not support.empty:
            nodes = pd.concat([nodes, support], ignore_index=True)
        relations = apply_mitigation_profiles(self.data['network'], self.data.get('network_mitigation'), scenario['shock'], scenario)
        network, paths = propagate_risk(
            nodes,
            relations,
            decay=DEMO_PARAMS["propagation_decay"],
            edge_scale=DEMO_PARAMS["network_edge_scale"],
            relation_weights=NETWORK_RELATION_WEIGHTS,
        )

        companies = self.data["companies"].merge(evaluations, on=["company_id", "company_name"])
        companies = companies.merge(network, on=["company_id", "company_name"])
        decisions = []
        for row in companies.itertuples():
            if getattr(row, 'evaluation_model', 'transition') == 'operating':
                decisions.append({'company_id': row.company_id, 'warning_level': '运行观察',
                                  'action': '按运行与履约风险分析，未适配转型融资模型'})
                continue
            encoded_params = getattr(row, 'reference_finance_params', None)
            finance_params = json.loads(encoded_params) if isinstance(encoded_params, str) and encoded_params else {}
            finance_params['round_intermediates'] = pd.notna(getattr(row, 'reference_finance_rounding', 0)) and bool(getattr(row, 'reference_finance_rounding', 0))
            decision = make_financing_decision(
                base_limit=row.base_limit,
                project_need=row.project_need,
                p_target=row.p_target,
                data_quality=row.data_quality,
                network_risk=row.network_risk,
                anomaly_score=row.effective_anomaly_score,
                params=finance_params,
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
            "prepared_network": prepare_network(nodes, relations, DEMO_PARAMS['network_edge_scale'], NETWORK_RELATION_WEIGHTS),
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
        if feature_row.iloc[0].get('evaluation_model') == 'operating':
            return {**results, 'company': row.iloc[0].to_dict(), 'lmdi': None,
                    'shap': pd.DataFrame(), 'shap_probability': None, 'top_paths': results['paths'][company_id]}
        shock = SCENARIOS[scenario_name]["shock"]
        if shock:
            scenario = SCENARIOS[scenario_name]
            sensitivity = scenario_sensitivity(feature_row, scenario)
            feature_row["energy_cost_ratio"] += shock * sensitivity * scenario.get("energy_cost_impact", 0.18)
            feature_row["cashflow_coverage"] -= shock * sensitivity * scenario.get("cashflow_impact", 0.45)
            feature_row["project_progress"] -= shock * sensitivity * scenario.get("progress_impact", 0.08)
        energy = self.data["energy"].loc[
            self.data["energy"]["company_id"] == company_id
        ]
        periods = sorted(energy["period"].unique())
        if len(periods) > 2:
            energy = energy.loc[energy["period"].isin([periods[0], periods[-1]])]
        probability_explanation = self.transition_engine.explain_probability(feature_row)
        final_probability = float(row.iloc[0]["p_target"])
        probability_explanation.update(
            final_probability=final_probability,
            scenario_adjustment_pp=(final_probability - probability_explanation["model_probability"]) * 100,
        )
        return {
            **results,
            "company": row.iloc[0].to_dict(),
            "lmdi": decompose_lmdi(energy, [
                {key: value for key, value in record.items() if key != "company_id"}
                for record in self.data.get("routes", []) if record["company_id"] == company_id
            ]),
            "shap": self.transition_engine.explain(feature_row),
            "shap_probability": probability_explanation,
            "top_paths": results["paths"][company_id],
        }
