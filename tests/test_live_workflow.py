import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from carbon_finance.finance import make_financing_decision
from carbon_finance.pipeline import CarbonFinancePipeline
from services.live_workflow import STAGES


def run_events(client, scenario="正常情景"):
    response = client.post("/api/v1/companies/A/analysis-workflow", json={"scenario": scenario})
    assert response.status_code == 200
    assert response.headers["x-accel-buffering"] == "no"
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


@pytest.mark.parametrize("scenario", ["正常情景", "天然气价格上涨30%"])
def test_actual_stage_results_match_existing_analysis(bank_headers, scenario):
    with TestClient(app) as client:
        client.headers.update(bank_headers)
        analysis = client.get("/api/v1/companies/A/analysis", params={"scenario": scenario}).json()
        events = run_events(client, scenario)
        expected = [(key, state) for key, _ in STAGES for state in ("running", "completed")]
        assert [(e["stage"], e["status"]) for e in events if e["type"] == "stage"] == expected
        assert events[-1]["type"] == "completed"
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        results = {e["stage"]: e["result"] for e in events if e.get("status") == "completed"}
        assert results["data"]["data_version"] == analysis["data_version"]
        assert results["data"]["energy_preview"]
        assert results["lmdi"]["total_change"] == pytest.approx(analysis["lmdi"]["total_change"])
        for key in ("p_target", "anomaly_score", "data_quality"):
            assert results["transition"][key] == pytest.approx(analysis["company"][key])
        assert results["transition"]["explanation"]["final_probability"] == pytest.approx(analysis["company"]["p_target"])
        for key in ("own_risk", "first_order_risk", "second_order_risk", "network_risk"):
            assert results["network"][key] == pytest.approx(analysis["company"][key])
        for key in ("final_limit", "suggested_rate", "raroc", "transition_support", "network_deduction"):
            assert results["finance"][key] == pytest.approx(analysis["company"][key])
        assert results["stress"]["stress"]["final_limit"] == pytest.approx(analysis["comparison"]["stress"]["final_limit"])
        assert results["review"]["human_review_required"] is True
        history = client.get("/api/v1/companies/A/analysis-workflows").json()["items"]
        assert history[0]["workflow_id"] == events[-1]["workflow_id"]
        assert history[0]["status"] == "completed"
        assert history[0]["events"][-1]["stage"] == "review"


def test_failures_stop_progress_and_are_audited(bank_headers, monkeypatch):
    def fail_finance(*args, **kwargs):
        raise ValueError("测试：融资计算不可用")

    monkeypatch.setattr("carbon_finance.pipeline.make_financing_decision", fail_finance)
    with TestClient(app) as client:
        client.headers.update(bank_headers)
        events = run_events(client)
        assert events[-1]["type"] == "error"
        assert events[-1]["stage"] == "finance"
        assert not any(e["type"] == "completed" for e in events)
        assert not any(e.get("stage") == "finance" and e.get("status") == "completed" for e in events)
        saved = client.get("/api/v1/companies/A/analysis-workflows").json()["items"][0]
        assert saved["status"] == "failed"


def test_workflow_requires_bank_and_rejects_import_payload(bank_headers):
    with TestClient(app) as client:
        endpoint = "/api/v1/companies/A/analysis-workflow"
        assert client.post(endpoint, json={}).status_code == 401
        client.headers.update(bank_headers)
        assert client.post(endpoint, json={"companies": [{"company_id": "injected"}]}).status_code == 422
        assert client.post(endpoint, json={"scenario": "不存在的情景"}).status_code == 400
        assert client.post("/api/v1/companies/NOT-HERE/analysis-workflow", json={}).status_code == 404
        assert client.post("/api/v1/companies/D/analysis-workflow", json={}).status_code == 400
        assert client.post("/api/v1/datasets/import", files={"file": ("data.csv", b"x")}).status_code == 403
        login = client.post("/api/v1/auth/login", json={"role": "企业端", "account": "company_demo", "password": "demo123"}).json()
        client.headers["Authorization"] = "Bearer " + login["token"]
        assert client.post(endpoint, json={}).status_code == 403
        assert client.get("/api/v1/companies/A/analysis-workflows").status_code == 403
        assert client.post("/api/v1/datasets/import", files={"file": ("data.csv", b"x")}).status_code == 410
