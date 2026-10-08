from fastapi.testclient import TestClient

from backend.main import app


def test_api_returns_dashboard_and_company_chain():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        metadata = client.get("/api/v1/metadata")
        assert metadata.status_code == 200
        assert len(metadata.json()["companies"]) == 6
        dashboard = client.get("/api/v1/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["summary"]["company_count"] == 6
        analysis = client.get(
            "/api/v1/companies/A/analysis",
            params={"scenario": "天然气价格上涨30%"},
        )
        assert analysis.status_code == 200
        payload = analysis.json()
        assert payload["comparison"]["stress"]["p_target"] < payload["comparison"]["normal"]["p_target"]
        assert len(payload["shap"]) == 5
