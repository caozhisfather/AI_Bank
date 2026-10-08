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
        return self

    def evaluate(
        self, features: pd.DataFrame, shock: float = 0.0
    ) -> pd.DataFrame:
        x = features[FEATURE_COLUMNS].copy()
        if shock:
            sensitivity = features["shock_sensitivity"].to_numpy()
            x["energy_cost_ratio"] += shock * sensitivity * 0.18
            x["cashflow_coverage"] -= shock * sensitivity * 0.45
            x["project_progress"] -= shock * sensitivity * 0.08
        probability = self.model.predict_proba(x)[:, 1]
        if shock:
            probability = np.clip(
                probability - shock * features["shock_sensitivity"].to_numpy() * 0.70,
                0.02,
                0.98,
            )
        anomaly_raw = -self.anomaly_model.decision_function(x)
        anomaly_score = np.clip((anomaly_raw + 0.18) / 0.36, 0, 1)
        completeness = x["data_completeness"].to_numpy()
        data_quality = np.clip(completeness * (1 - 0.28 * anomaly_score), 0.55, 1)
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
