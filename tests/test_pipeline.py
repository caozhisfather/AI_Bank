from carbon_finance.pipeline import CarbonFinancePipeline


def test_pressure_scenario_changes_full_decision_chain():
    pipeline = CarbonFinancePipeline()
    normal = pipeline.company_detail("A", "正常情景")
    stress = pipeline.company_detail("A", "天然气价格上涨30%")
    assert {"base_limit", "project_need", "final_limit"}.issubset(
        normal["companies"].columns
    )
    assert 0.5 <= normal["model_auc"] <= 1
    assert len(normal["shap"]) == 5
    assert stress["company"]["p_target"] < normal["company"]["p_target"]
    assert stress["company"]["network_risk"] > normal["company"]["network_risk"]
    assert stress["company"]["final_limit"] < normal["company"]["final_limit"]
