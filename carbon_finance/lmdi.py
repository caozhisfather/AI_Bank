from __future__ import annotations

import math

import pandas as pd


def _log_mean(x: float, y: float) -> float:
    if x <= 0 or y <= 0:
        return 0.0
    if math.isclose(x, y, rel_tol=1e-12):
        return x
    return (x - y) / (math.log(x) - math.log(y))


def decompose_lmdi(records: pd.DataFrame) -> dict[str, float]:
    """Additive LMDI decomposition for two periods and multiple energy types."""
    required = {"period", "output", "energy_type", "energy", "emission_factor"}
    if not required.issubset(records.columns):
        raise ValueError(f"LMDI 数据缺少字段：{sorted(required - set(records.columns))}")
    periods = sorted(records["period"].unique())
    if len(periods) != 2:
        raise ValueError("LMDI 分解需要且仅需要两个观察期")

    frames = []
    for period in periods:
        part = records[records["period"] == period].copy()
        output_values = part["output"].unique()
        if len(output_values) != 1 or output_values[0] <= 0:
            raise ValueError("每个观察期必须有一个大于零的统一产量")
        part["emissions"] = part["energy"] * part["emission_factor"]
        total_energy = part["energy"].sum()
        part["energy_intensity"] = total_energy / output_values[0]
        part["energy_share"] = part["energy"] / total_energy
        frames.append(part.set_index("energy_type"))

    base, current = frames
    common = base.index.intersection(current.index)
    effects = {"activity": 0.0, "efficiency": 0.0, "energy_structure": 0.0}
    for energy_type in common:
        b, c = base.loc[energy_type], current.loc[energy_type]
        weight = _log_mean(float(c.emissions), float(b.emissions))
        effects["activity"] += weight * math.log(float(c.output / b.output))
        effects["efficiency"] += weight * math.log(
            float(c.energy_intensity / b.energy_intensity)
        )
        structure_factor = (c.energy_share * c.emission_factor) / (
            b.energy_share * b.emission_factor
        )
        effects["energy_structure"] += weight * math.log(float(structure_factor))

    base_emissions = float(base["emissions"].sum())
    current_emissions = float(current["emissions"].sum())
    effects.update(
        {
            "base_emissions": base_emissions,
            "current_emissions": current_emissions,
            "total_change": current_emissions - base_emissions,
            "residual": current_emissions - base_emissions - sum(effects.values()),
        }
    )
    return effects
