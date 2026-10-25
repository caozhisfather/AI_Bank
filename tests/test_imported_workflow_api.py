import json
import pytest

from fastapi.testclient import TestClient

from backend.main import app
from services.dataset_service import dataset_store


SAMPLE = [
    {"company_id": "X01", "company_name": "测试钢铁", "base_limit": 1500, "project_need": 500,
     "project_progress": 0.82, "fund_usage_match": 0.94, "data_completeness": 0.96,
     "intensity_trend": 0.12, "network_exposure": 0.25},
    {"company_id": "X02", "company_name": "测试能源", "base_limit": 900, "project_need": 300,
     "project_progress": 0.68, "fund_usage_match": 0.85, "data_completeness": 0.90,
     "intensity_trend": 0.07, "network_exposure": 0.35},
]


def test_json_import_and_langgraph_workflow(bank_headers):
    with TestClient(app) as client:
        client.headers.update(bank_headers)
        dataset = dataset_store.response(dataset_store.import_file("companies.json", json.dumps(SAMPLE).encode()))
        assert dataset["rows"] == 2
        assert dataset["validation"]["valid"] is True

        response = client.post("/api/v1/agent-workflows/run", json={
            "dataset_id": dataset["dataset_id"],
            "options": {"industry": "钢铁", "scenario": "正常情景", "agent_mode": "offline"},
        })
        assert response.status_code == 200
        payload = response.json()
        assert payload["workflow"]["orchestration"]["engine"] == "langgraph"
        assert len(payload["workflow"]["steps"]) == 5
        assert payload["agent_mode"] == "offline_deterministic"
        assert len(payload["analysis"]["financing"]) == 2
        assert payload["workflow"]["human_review_required"] is True

        workflow_id = payload["workflow"]["workflow_id"]
        saved = client.get(f"/api/v1/agent-workflows/{workflow_id}")
        assert saved.status_code == 200
        assert saved.json()["workflow"]["workflow_id"] == workflow_id
        history = client.get("/api/v1/agent-workflows", params={"limit": 1})
        assert history.status_code == 200
        assert history.json()["items"][0]["workflow_id"] == workflow_id


def test_csv_import_and_security_rejections(bank_headers):
    csv_content = "company_id,company_name,base_limit,project_need\nX01,测试企业,1000,300\n"
    with TestClient(app) as client:
        client.headers.update(bank_headers)
        imported = dataset_store.response(dataset_store.import_file("companies.csv", csv_content.encode()))
        assert imported["preview"][0]["base_limit"] == 1000
        bad_type = client.post("/api/v1/datasets/import", files={"file": ("payload.exe", b"bad", "application/octet-stream")})
        assert bad_type.status_code == 403
        with pytest.raises(ValueError):
            dataset_store.import_file("nested.json", b'[{"company_id":"X","x":{"bad":1}}]')
        with pytest.raises(ValueError):
            dataset_store.import_file("payload.exe", b"bad")


def test_template_and_agent_capabilities(bank_headers):
    with TestClient(app) as client:
        client.headers.update(bank_headers)
        template = client.get("/api/v1/datasets/template")
        assert template.status_code == 200
        assert "company_id" in template.text
        assert "attachment" in template.headers["content-disposition"]

        capabilities = client.get("/api/v1/agent-workflows/capabilities")
        assert capabilities.status_code == 200
        payload = capabilities.json()
        assert payload["orchestrator"] == "langgraph"
        assert payload["tool_framework"] == "langchain"
        assert payload["deepagents"]["installed"] is True
        assert payload["human_review_required"] is True


def test_missing_dataset_and_invalid_options(bank_headers):
    with TestClient(app) as client:
        client.headers.update(bank_headers)
        assert client.get("/api/v1/agent-workflows/WF-NOTFOUND").status_code == 404
        assert client.post("/api/v1/agent-workflows/run", json={"dataset_id": "DS-NOTFOUND", "options": {}}).status_code == 404
        assert client.post("/api/v1/agent-workflows/run", json={"dataset_id": "DS-NOTFOUND", "options": {"propagation_decay": 2}}).status_code == 422


def test_frontend_flat_contract_and_agent_selection(bank_headers):
    with TestClient(app) as client:
        client.headers.update(bank_headers)
        dataset = dataset_store.response(dataset_store.import_file("company.json", json.dumps(SAMPLE[0]).encode()))
        assert dataset["row_count"] == 1
        assert dataset["data_quality"] > 0

        response = client.post("/api/v1/agent-workflows/run", json={
            "dataset_id": dataset["dataset_id"],
            "industry": "钢铁",
            "scenario": "天然气价格上涨30%",
            "transition_support_ratio": 0.25,
            "propagation_decay": 0.60,
            "network_risk_weight": 0.35,
            "execution_mode": "offline",
            "enabled_agents": ["data", "finance", "compliance"],
        })
        assert response.status_code == 200
        payload = response.json()
        assert payload["analysis"]["scenario"] == "天然气价格上涨30%"
        assert payload["workflow"]["orchestration"]["enabled_agents"] == ["data", "finance", "compliance"]
        assert [step["id"] for step in payload["workflow"]["steps"]] == [
            "data-agent", "finance-agent", "compliance-agent"
        ]


def test_six_table_structured_json_is_enriched_for_agents(bank_headers):
    structured = {
        "companies": [{"company_id": "S01", "company_name": "六表钢铁", "industry": "钢铁", "base_limit": 3000, "project_need": 1000}],
        "energy_performance": [
            {"company_id": "S01", "period": "2025-01", "output": 100, "energy_type": "coal", "energy": 40, "emission_factor": 2.5},
            {"company_id": "S01", "period": "2025-12", "output": 105, "energy_type": "coal", "energy": 32, "emission_factor": 2.5},
        ],
        "transition_projects": [{"company_id": "S01", "project_progress": 0.86, "milestone_delay_days": 3, "project_need": 1000}],
        "fund_usage": [{"company_id": "S01", "fund_usage_match": 0.96, "own_fund_arrival": 0.91}],
        "network_edges": [{"source": "S01", "target": "S02", "weight": 0.31, "relation_type": "供应依赖"}],
        "external_risks": [{"scenario": "天然气价格上涨30%", "driver": "天然气价格", "change": 0.30}],
    }
    with TestClient(app) as client:
        client.headers.update(bank_headers)
        payload = dataset_store.response(dataset_store.import_file("six-tables.json", json.dumps(structured).encode()))
        assert payload["validation"]["structured"] is True
        assert len(payload["source_tables"]) == 6
        assert payload["preview"][0]["project_progress"] == 0.86
        assert payload["preview"][0]["fund_usage_match"] == 0.96
        assert payload["preview"][0]["intensity_trend"] > 0

        workflow = client.post("/api/v1/agent-workflows/run", json={"dataset_id": payload["dataset_id"], "scenario": "电价上涨20%"})
        assert workflow.status_code == 200
        assert workflow.json()["analysis"]["scenario"] == "电价上涨20%"

        template = client.get("/api/v1/datasets/structured-template")
        assert template.status_code == 200
        assert len(template.json()) == 6
