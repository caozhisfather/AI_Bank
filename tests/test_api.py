from fastapi.testclient import TestClient
import pytest

from backend.main import app


def test_api_returns_dashboard_and_company_chain(bank_headers):
    with TestClient(app) as client:
        client.headers.update(bank_headers)
        assert client.get("/health").json() == {"status": "ok"}
        metadata = client.get("/api/v1/metadata")
        assert metadata.status_code == 200
        assert len(metadata.json()["companies"]) == 36
        assert metadata.json()["terminals"]["银行端"] == ['转型可信度评价','园区风险分析','融资决策','审核任务清单']
        assert '压力测试' not in metadata.json()['terminals']['银行端']
        assert metadata.json()["terminals"]["银行端"][-1] == "审核任务清单"
        assert metadata.json()["terminals"]["企业端"][3] == "转型可信度"
        dashboard = client.get("/api/v1/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["summary"]["company_count"] == 36
        analysis = client.get(
            "/api/v1/companies/A/analysis",
            params={"scenario": "天然气价格上涨30%"},
        )
        assert analysis.status_code == 200
        payload = analysis.json()
        assert payload["lmdi"]["process"] is None
        assert payload["lmdi"]["process_available"] is False
        lmdi = payload["lmdi"]
        assert lmdi["total_change_percentage"] == pytest.approx(lmdi["total_change"] / lmdi["base_emissions"] * 100)
        assert sum(value for value in lmdi["effect_percentages"].values() if value is not None) == pytest.approx(lmdi["total_change_percentage"])
        assert "主要减排来源" in payload["lmdi"]["conclusion"]
        assert payload['lmdi']['assessment_summary'] == '能效改善主导'
        assert payload["comparison"]["stress"]["p_target"] < payload["comparison"]["normal"]["p_target"]
        assert len(payload["shap"]) == 5
        probability_shap = payload['shap_probability']
        assert probability_shap['unit'] == 'percentage_points'
        assert len(probability_shap['items']) == 10
        assert probability_shap['final_probability'] == payload['company']['p_target']
        assert probability_shap['base_probability'] + (probability_shap['total_contribution_pp'] + probability_shap['scenario_adjustment_pp']) / 100 == pytest.approx(probability_shap['final_probability'], abs=1e-6)
        company = payload["company"]
        assert company["raroc_threshold"] == 0.085
        assert isinstance(company["raroc_before_adjustment"], float)
        assert company["risk_capital"] > 0
        assert company["expected_loss"] >= 0
        credibility = payload["transition_credibility"]
        assert credibility["method"] == "quality_adjusted_probability"
        assert credibility["max_score"] == 100
        assert credibility["p_target"] == company["p_target"]
        assert credibility["data_quality"] == company["data_quality"]
        assert credibility["score"] == pytest.approx(100 * company["p_target"] * company["data_quality"])
        normal = payload["comparison"]["normal"]
        assert credibility["score"] < 100 * normal["p_target"] * normal["data_quality"]
        assert len(payload["carbon_trend"]) == 12
        evidence = payload["transition_evidence"]
        assert set(evidence) == {"emissions", "project", "funds", "data"}
        assert evidence["emissions"]["base_period"] == "2025-01"
        assert evidence["emissions"]["current_period"] == "2025-12"
        assert evidence["emissions"]["efficiency_effect"] == payload["lmdi"]["efficiency"]
        assert evidence["emissions"]["energy_structure_effect"] == payload["lmdi"]["energy_structure"]
        assert evidence["emissions"]["net_change"] == payload["lmdi"]["total_change"]
        assert evidence["project"]["progress"] == payload["project"]["progress"]
        assert evidence["project"]["milestone_delay_days"] == 3
        assert evidence["funds"]["usage_match"] == 0.96
        assert evidence["funds"]["own_fund_arrival"] == 0.91
        assert evidence["data"]["completeness"] == pytest.approx(0.969295017649203)
        assert company['data_quality'] == pytest.approx(.95)
        assert evidence["data"]["rule_quality"] == company["data_quality"]
        assert evidence["data"]["anomaly_score"] == company["anomaly_score"]
        assert payload["network_graph"]["nodes"]
        assert payload["network_graph"]["edges"]
        exposure = payload["affected_credit_exposure"]
        assert exposure["basis"] == "base_limit"
        assert exposure["source_company_id"] == "A"
        assert exposure["total_exposure"] == 24681
        assert exposure["company_count"] == 11
        assert {item["company_id"] for item in exposure["companies"]} == {'A','E','F','P01','P23','B','P02','P04','P06','P22','P25'}
        graph = payload['network_graph']
        assert len(graph['nodes']) == 36  # No hidden 14-node cutoff.
        assert {item['dependency_class'] for item in graph['edges']} == {'supply', 'energy', 'infra'}
        assert graph['pending_edges'] == []
        assert len(graph['edges']) == 101
        assert {node['company_id'] for node in graph['nodes'] if node['node_type']=='energy'} == {'D','P26','P27'}
        assert {node['company_id'] for node in graph['nodes'] if node['node_type']=='infra'} == {'P28','P29','P30'}
        assert all(item['effective_weight'] > 0 for item in graph['edges'])
        assert all(item['dependent_id']==item['target'] and item['provider_id']==item['source'] for item in graph['edges'])
        assert all(item['risk_delta']==pytest.approx(item['risk']-item['baseline_risk']) for item in graph['nodes'])
        explanation=payload['network_analysis']
        assert all(path['node_ids'][-1]=='A' for path in explanation['incoming_paths'])
        assert all(path['node_ids'][0]=='A' for path in explanation['outgoing_paths'])
        for order,field in [(1,'first_order_risk'),(2,'second_order_risk')]:
            assert sum(p['contribution'] for p in explanation['incoming_paths'] if p['order']==order)==pytest.approx(company[field])
        assert all(path['contribution']==pytest.approx(path['gross_contribution']-path['mitigation_contribution']) for path in explanation['incoming_paths'])
        assert sum(edge['direct_contribution'] for edge in graph['edges'] if edge['target']=='A')==pytest.approx(company['first_order_risk'])
        assert sum(edge['baseline_direct_contribution'] for edge in graph['edges'] if edge['target']=='A')==pytest.approx(normal['first_order_risk'])
        assert any(edge['mitigation_source'] and edge['mitigation_status']=='模拟参数·未核验' for edge in graph['edges'])
        assert all(edge['commodity'] and '模拟' in edge['data_source'] for edge in graph['edges'])
        workflow = client.get(
            "/api/v1/companies/A/agent-workflow",
            params={"scenario": "天然气价格上涨30%"},
        )
        assert workflow.status_code == 200
        workflow_payload = workflow.json()
        assert [step["id"] for step in workflow_payload["steps"]] == [
            "data-agent", "transition-agent", "network-agent", "finance-agent", "compliance-agent"
        ]
        assert workflow_payload["human_review_required"] is True
        assert all(step["evidence"] for step in workflow_payload["steps"])
