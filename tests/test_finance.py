import math

import pytest

from carbon_finance.finance import make_financing_decision


def test_more_network_risk_reduces_limit():
    common = dict(
        base_limit=3000,
        project_need=1000,
        p_target=0.82,
        data_quality=0.95,
        anomaly_score=0.1,
    )
    normal = make_financing_decision(network_risk=0.16, **common)
    stress = make_financing_decision(network_risk=0.31, **common)
    assert normal["transition_support"] > 0
    assert stress["network_deduction"] > normal["network_deduction"]
    assert stress["final_limit"] < normal["final_limit"]
    assert normal["raroc_passed"]


@pytest.mark.parametrize("threshold_gap", [-0.01, 0.0, 0.01])
def test_raroc_keeps_initial_result_and_reconciles_pricing_adjustment(threshold_gap):
    inputs = dict(
        base_limit=3000, project_need=1000, p_target=0.82,
        data_quality=0.95, network_risk=0.16, anomaly_score=0.1,
    )
    baseline = make_financing_decision(**inputs)
    threshold = baseline["raroc_before_adjustment"] + threshold_gap
    result = make_financing_decision(**inputs, params={"raroc_threshold": threshold})
    reconstructed = (
        result["loan_income_before_adjustment"] - result["expected_loss"] - result["operating_cost"]
    ) / result["risk_capital"]
    assert math.isclose(result["raroc_before_adjustment"], reconstructed, abs_tol=1e-12)
    assert result["raroc_before_adjustment"] == baseline["raroc_before_adjustment"]
    assert result["raroc_threshold"] == threshold
    assert math.isclose(
        result["loan_income_before_adjustment"], result["final_limit"] * result["initial_rate"],
        abs_tol=1e-9,
    )
    adjusted = (
        result["final_limit"] * result["suggested_rate"] - result["expected_loss"] - result["operating_cost"]
    ) / result["risk_capital"]
    assert math.isclose(result["raroc"], adjusted, abs_tol=1e-12)
    if threshold_gap > 0:
        assert result["raroc_before_adjustment"] < threshold
        assert result["suggested_rate"] > result["initial_rate"]
        assert math.isclose(result["raroc"], threshold, abs_tol=1e-12)
    else:
        assert result["suggested_rate"] == result["initial_rate"]
        assert result["raroc"] == result["raroc_before_adjustment"]
