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
