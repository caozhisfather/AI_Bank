from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from carbon_finance.config import DATA_DIR, FEATURE_COLUMNS, RANDOM_STATE
from carbon_finance.reference_case import apply_reference_case_files


def generate_training(rng: np.random.Generator, size: int = 900) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "lmdi_efficiency_share": rng.uniform(0.05, 0.75, size),
            "lmdi_energy_share": rng.uniform(0.02, 0.55, size),
            "intensity_trend": rng.normal(0.07, 0.09, size).clip(-0.18, 0.32),
            "project_progress": rng.beta(4, 2, size),
            "milestone_delay_days": rng.gamma(2.2, 10, size).clip(0, 100),
            "fund_usage_match": rng.beta(8, 2, size),
            "own_fund_arrival": rng.beta(5, 2, size),
            "cashflow_coverage": rng.uniform(0.5, 2.4, size),
            "energy_cost_ratio": rng.uniform(0.10, 0.46, size),
            "data_completeness": rng.beta(10, 1.7, size),
        }
    )
    logit = (
        -5.7
        + 1.6 * df["lmdi_efficiency_share"]
        + 1.0 * df["lmdi_energy_share"]
        + 3.0 * df["intensity_trend"]
        + 2.5 * df["project_progress"]
        - 0.025 * df["milestone_delay_days"]
        + 1.4 * df["fund_usage_match"]
        + 1.0 * df["own_fund_arrival"]
        + 0.55 * df["cashflow_coverage"]
        - 2.0 * df["energy_cost_ratio"]
        + 1.0 * df["data_completeness"]
        + rng.normal(0, 0.45, size)
    )
    probability = 1 / (1 + np.exp(-logit))
    df["target_met"] = rng.binomial(1, probability)
    return df


def main() -> None:
    from scripts.rebuild_park_data import prepare
    report = prepare(DATA_DIR)
    print(f"Generated {report['subject_count']} typed simulated subjects in {DATA_DIR}")


if __name__ == "__main__":
    main()
