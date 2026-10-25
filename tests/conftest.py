import pytest
from fastapi.testclient import TestClient

from backend.main import app
import backend.auth as auth
import backend.routers.reviews as reviews
import backend.routers.workflows as workflows
import services.analysis_service as analysis
import services.dataset_service as datasets
from services.business_store import BusinessStore
from services.persistent_store import PersistentStore


@pytest.fixture(autouse=True)
def isolated_platform(tmp_path, monkeypatch):
    store = BusinessStore(tmp_path / "business.db")
    for module in (auth, reviews, analysis):
        monkeypatch.setattr(module, "business_store", store)
    legacy = PersistentStore(tmp_path / "legacy.db")
    monkeypatch.setattr(datasets, "persistent_store", legacy)
    monkeypatch.setattr(workflows, "persistent_store", legacy)
    monkeypatch.setenv("PLATFORM_DEMO_PASSWORD", "demo123")
    datasets.dataset_store._items.clear()
    workflows._workflow_runs.clear()
    analysis.get_analysis_service.cache_clear()
    yield store
    analysis.get_analysis_service.cache_clear()


@pytest.fixture
def bank_headers():
    with TestClient(app) as client:
        result = client.post("/api/v1/auth/login", json={"account": "bank_demo", "password": "demo123", "role": "银行端"})
        assert result.status_code == 200
        return {"Authorization": f"Bearer {result.json()['token']}"}
