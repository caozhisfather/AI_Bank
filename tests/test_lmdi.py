import math

import pandas as pd

from carbon_finance.lmdi import decompose_lmdi


def test_lmdi_effects_reconcile_to_total_change():
    records = pd.DataFrame(
        [
            [2025, 100, "coal", 40, 2.5],
            [2025, 100, "power", 20, 0.55],
            [2026, 106, "coal", 31, 2.5],
            [2026, 106, "power", 26, 0.55],
        ],
        columns=["period", "output", "energy_type", "energy", "emission_factor"],
    )
    result = decompose_lmdi(records)
    reconstructed = result["activity"] + result["efficiency"] + result["energy_structure"]
    assert math.isclose(reconstructed, result["total_change"], abs_tol=1e-8)
    assert abs(result["residual"]) < 1e-8
    assert result["activity"] > 0
    assert result["efficiency"] < 0
