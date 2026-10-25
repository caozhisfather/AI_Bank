from carbon_finance.pipeline import CarbonFinancePipeline
from carbon_finance.config import FEATURE_COLUMNS
import pytest


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


def test_all_documented_stress_scenarios_run_full_chain():
    pipeline = CarbonFinancePipeline()
    normal = pipeline.company_detail("A", "正常情景")["company"]
    scenarios = ["天然气价格上涨30%", "电价上涨20%", "煤价上涨25%", "碳价上涨50%", "核心客户需求下降20%"]

    for scenario in scenarios:
        stressed = pipeline.company_detail("A", scenario)["company"]
        assert stressed["p_target"] < normal["p_target"]
        assert stressed["network_risk"] > normal["network_risk"]
        assert stressed["final_limit"] < normal["final_limit"]


def test_probability_shap_reconstructs_predictions_with_separate_scenario_adjustment():
    pipeline = CarbonFinancePipeline()
    baselines = []
    for company_id in ['A', 'F']:
        for scenario in ['正常情景', '天然气价格上涨30%', '核心客户需求下降20%']:
            detail = pipeline.company_detail(company_id, scenario)
            explanation = detail['shap_probability']
            assert explanation['unit'] == 'percentage_points'
            assert explanation['background_source'] == 'training_split'
            assert explanation['background_size'] == 100
            items = explanation['items']
            assert {item['feature'] for item in items} == set(FEATURE_COLUMNS)
            assert len(items) == 10
            magnitudes = [abs(item['contribution_pp']) for item in items]
            assert magnitudes == sorted(magnitudes, reverse=True)
            for item in items:
                assert item['contribution_pp'] == pytest.approx(100 * item['contribution'])
            total_pp = sum(item['contribution_pp'] for item in items)
            assert explanation['total_contribution_pp'] == pytest.approx(total_pp)
            assert explanation['base_probability'] + total_pp / 100 == pytest.approx(explanation['model_probability'], abs=1e-6)
            assert explanation['base_probability'] + (total_pp + explanation['scenario_adjustment_pp']) / 100 == pytest.approx(detail['company']['p_target'], abs=1e-6)
            if scenario == '正常情景':
                assert explanation['scenario_adjustment_pp'] == pytest.approx(0)
            else:
                assert explanation['scenario_adjustment_pp'] < 0
            baselines.append(explanation['base_probability'])
    assert max(baselines) == pytest.approx(min(baselines))
