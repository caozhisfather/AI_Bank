from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from carbon_finance.config import DATA_DIR, FEATURE_COLUMNS, RANDOM_STATE


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
    rng = np.random.default_rng(RANDOM_STATE)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    companies = pd.DataFrame(
        [
            ["A", "恒岳钢铁", "钢铁", 3000, 1000, 0.31, 0.078, 0.067, 0.091, "高炉节能与绿电替代"],
            ["B", "华新建材", "水泥", 2200, 720, 0.26, 0.082, 0.073, 0.087, "窑炉余热回收改造"],
            ["C", "临港新材", "钢铁", 1800, 560, 0.35, 0.085, 0.071, 0.095, "短流程电炉升级"],
            ["D", "清源能源", "公用工程", 2600, 850, 0.42, 0.076, 0.064, 0.089, "园区清洁能源供应"],
            ["E", "远达物流", "园区物流", 1200, 380, 0.18, 0.088, 0.075, 0.093, "新能源运输设备更新"],
            ["F", "中辰化工", "化工", 2400, 900, 0.46, 0.081, 0.069, 0.097, "蒸汽系统能效改造"],
        ],
        columns=["company_id", "company_name", "industry", "base_limit", "project_need", "shock_sensitivity", "pd_base", "carbon_intensity", "target_intensity", "project_name"],
    )
    feature_values = [
        ["A", "恒岳钢铁", .61, .35, .14, .86, 3, .96, .91, 1.72, .28, .97, .31],
        ["B", "华新建材", .49, .31, .10, .75, 12, .91, .84, 1.46, .32, .94, .26],
        ["C", "临港新材", .55, .40, .13, .81, 7, .94, .88, 1.61, .25, .96, .35],
        ["D", "清源能源", .43, .46, .09, .69, 18, .88, .76, 1.31, .39, .92, .42],
        ["E", "远达物流", .35, .28, .07, .72, 10, .93, .80, 1.54, .19, .95, .18],
        ["F", "中辰化工", .38, .22, .04, .58, 31, .73, .62, 1.08, .43, .86, .46],
    ]
    features = pd.DataFrame(feature_values, columns=["company_id", "company_name", *FEATURE_COLUMNS, "shock_sensitivity"])
    energy_rows = []
    settings = {
        "A": (100, 106, [("coal", 38, 31, 2.50), ("gas", 18, 18, 2.00), ("electricity", 22, 26, .55)]),
        "B": (90, 93, [("coal", 34, 29, 2.50), ("gas", 12, 13, 2.00), ("electricity", 20, 22, .55)]),
        "C": (80, 85, [("coal", 24, 17, 2.50), ("gas", 10, 11, 2.00), ("electricity", 25, 31, .55)]),
        "D": (70, 75, [("coal", 16, 11, 2.50), ("gas", 25, 27, 2.00), ("electricity", 18, 23, .55)]),
        "E": (60, 64, [("diesel", 18, 14, 2.68), ("electricity", 8, 13, .55)]),
        "F": (85, 87, [("coal", 20, 19, 2.50), ("gas", 29, 28, 2.00), ("electricity", 19, 20, .55)]),
    }
    for company_id, (base_output, current_output, fuels) in settings.items():
        for fuel, base_energy, current_energy, factor in fuels:
            energy_rows.extend([[company_id, 2025, base_output, fuel, base_energy, factor], [company_id, 2026, current_output, fuel, current_energy, factor]])
    energy = pd.DataFrame(energy_rows, columns=["company_id", "period", "output", "energy_type", "energy", "emission_factor"])
    edges = pd.DataFrame(
        [
            ["D", "A", .52, "能源依赖"], ["D", "B", .44, "能源依赖"], ["D", "F", .58, "能源依赖"],
            ["A", "C", .31, "供应依赖"], ["C", "B", .26, "供应依赖"], ["B", "E", .34, "客户依赖"],
            ["F", "A", .22, "供应依赖"], ["A", "E", .28, "客户依赖"], ["E", "F", .18, "物流依赖"],
        ], columns=["source", "target", "weight", "relation_type"]
    )
    training = generate_training(rng)
    companies.to_csv(DATA_DIR / "companies.csv", index=False, encoding="utf-8-sig")
    features.to_csv(DATA_DIR / "transition_features.csv", index=False, encoding="utf-8-sig")
    energy.to_csv(DATA_DIR / "energy_performance.csv", index=False, encoding="utf-8-sig")
    edges.to_csv(DATA_DIR / "network_edges.csv", index=False, encoding="utf-8-sig")
    training.to_csv(DATA_DIR / "training_samples.csv", index=False, encoding="utf-8-sig")
    print(f"Generated demo data in {DATA_DIR}")


if __name__ == "__main__":
    main()
