from __future__ import annotations

import numpy as np
import pandas as pd
import warnings
from lightgbm import LGBMClassifier
from shap import TreeExplainer
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from .config import FEATURE_COLUMNS, FEATURE_LABELS, RANDOM_STATE


def scenario_sensitivity(features, scenario):
    field = {'天然气价格':'gas_sensitivity', '工业电价':'electricity_sensitivity',
             '动力煤价格':'coal_sensitivity', '碳配额价格':'carbon_sensitivity',
             '核心客户需求':'demand_sensitivity'}.get((scenario or {}).get('driver'))
    return features[field] if field in features else features['shock_sensitivity']


class TransitionEngine:
    def __init__(self) -> None:
        self.model = LGBMClassifier(
            n_estimators=140,
            learning_rate=0.035,
            num_leaves=15,
            max_depth=5,
            min_child_samples=18,
            reg_lambda=1.0,
            random_state=RANDOM_STATE,
            n_jobs=1,
            verbosity=-1,
        )
        self.anomaly_model = IsolationForest(
            n_estimators=160,
            contamination=0.06,
            random_state=RANDOM_STATE,
            n_jobs=1,
        )
        self.auc = float("nan")

    def fit(self, training: pd.DataFrame) -> "TransitionEngine":
        x = training[FEATURE_COLUMNS]
        y = training["target_met"]
        x_train, x_test, y_train, y_test = train_test_split(
            x, y, test_size=0.25, stratify=y, random_state=RANDOM_STATE
        )
        self.model.fit(x_train, y_train)
        self.auc = float(roc_auc_score(y_test, self.model.predict_proba(x_test)[:, 1]))
        self.anomaly_model.fit(x_train)
        # Use a fixed training-only reference set for probability-space SHAP.
        # A raw-margin SHAP value cannot be multiplied by 100 to obtain percentage points.
        background = x_train.sample(n=min(100, len(x_train)), random_state=RANDOM_STATE)
        self.probability_explainer = TreeExplainer(
            self.model, data=background, model_output="probability",
            feature_perturbation="interventional",
        )
        return self

    def evaluate(
        self, features: pd.DataFrame, shock: float = 0.0, scenario: dict | None = None
    ) -> pd.DataFrame:
        x = features[FEATURE_COLUMNS].copy()
        scenario = scenario or {}
        if shock:
            sensitivity = scenario_sensitivity(features, scenario).to_numpy()
            x["energy_cost_ratio"] += shock * sensitivity * scenario.get("energy_cost_impact", 0.18)
            x["cashflow_coverage"] -= shock * sensitivity * scenario.get("cashflow_impact", 0.45)
            x["project_progress"] -= shock * sensitivity * scenario.get("progress_impact", 0.08)
        probability = self.model.predict_proba(x)[:, 1]
        if shock:
            # A pure adverse cost/demand scenario cannot improve the target probability
            # through an unconstrained tree split. Explain this cap as scenario adjustment.
            probability = np.minimum(probability, self.model.predict_proba(features[FEATURE_COLUMNS])[:, 1])
            probability = np.clip(
                probability - shock * sensitivity * scenario.get("probability_penalty", 0.70),
                0.02,
                0.98,
            )
        # A hypothetical price shock changes operating outcomes, not the quality of filed facts.
        anomaly_raw = -self.anomaly_model.decision_function(features[FEATURE_COLUMNS])
        anomaly_score = np.clip((anomaly_raw + 0.18) / 0.36, 0, 1)
        completeness = x["data_completeness"].to_numpy()
        anomaly_penalty = 0.06 * anomaly_score + 0.40 * np.clip(anomaly_score - 0.40, 0, 1)
        data_quality = np.clip(completeness * (1 - anomaly_penalty), 0.55, 1)
        result = features[["company_id", "company_name"]].copy()
        result["p_target"] = probability
        result["transition_score"] = np.round(probability * 1000).astype(int)
        result["anomaly_score"] = anomaly_score
        result["data_quality"] = data_quality
        return result

    def explain(self, feature_row: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
        x = feature_row[FEATURE_COLUMNS]
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="LightGBM binary classifier with TreeExplainer shap values output has changed",
            )
            values = TreeExplainer(self.model).shap_values(x)
        if isinstance(values, list):
            values = values[-1]
        values = np.asarray(values)
        if values.ndim == 3:
            values = values[:, :, -1]
        contributions = values[0]
        result = pd.DataFrame(
            {
                "feature": FEATURE_COLUMNS,
                "label": [FEATURE_LABELS[item] for item in FEATURE_COLUMNS],
                "value": x.iloc[0].to_numpy(),
                "contribution": contributions,
            }
        )
        return result.reindex(result.contribution.abs().sort_values(ascending=False).index).head(top_n)

    def explain_probability(self, feature_row: pd.DataFrame) -> dict:
        """Explain the model probability itself, before external scenario adjustments."""
        x = feature_row[FEATURE_COLUMNS]
        values = self.probability_explainer.shap_values(x)
        if isinstance(values, list):
            values = values[-1]
        values = np.asarray(values)
        if values.ndim == 3:
            values = values[:, :, -1]
        contributions = values[0]
        baseline = float(np.asarray(self.probability_explainer.expected_value).reshape(-1)[-1])
        probability = float(self.model.predict_proba(x)[0, 1])
        if not np.isclose(baseline + contributions.sum(), probability, atol=1e-6, rtol=0):
            raise ValueError("SHAP 概率贡献合计与模型预测不一致")
        items = [
            {"feature": feature, "label": FEATURE_LABELS[feature], "value": float(x.iloc[0][feature]),
             "contribution": float(contribution), "contribution_pp": float(contribution * 100)}
            for feature, contribution in zip(FEATURE_COLUMNS, contributions)
        ]
        items.sort(key=lambda item: abs(item["contribution"]), reverse=True)
        return {
            "method": "interventional_probability_shap", "unit": "percentage_points",
            "background_source": "training_split", "background_size": len(self.probability_explainer.data),
            "base_probability": baseline, "model_probability": probability,
            "total_contribution_pp": float(contributions.sum() * 100), "items": items,
        }
