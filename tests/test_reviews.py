import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from services.business_store import BusinessStore


def login(client, account="company_demo"):
    response = client.post("/api/v1/auth/login", json={"account": account, "password": "demo123", "role": "银行端" if account == "bank_demo" else "企业端"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def sync_body(client, headers, extreme=False):
    status = client.get("/api/v1/enterprise/data-status", headers=headers).json()
    energy = status["energy_records"]
    for row in energy:
        row["output"] *= 0.7
        row["energy"] *= 1.1
    features = status["features"]
    if extreme:
        features.update(project_progress=0.02, fund_usage_match=0.05, cashflow_coverage=0.05, energy_cost_ratio=0.99, data_completeness=0.9)
    return {"request_id": str(uuid4()), "source_system": "测试企业 EMS", "reporting_period": "2026-01", "features": features, "energy_records": energy}


def submit(client, headers, task, corrections=None):
    response = client.post("/api/v1/enterprise/evidence", headers=headers, data={"task_id": task["id"], "revision": task["revision"], "version_id": task["version_id"], "explanation": "设备检修期间生产调整，提交检修及计量核验说明。", "corrections": json.dumps(corrections or {})}, files={"files": ("检修证明.txt", "检修期核验证明，适用于当前企业和报告期间。".encode(), "text/plain")})
    assert response.status_code == 200, response.text
    return response.json()


def test_company_isolation_and_bank_review_permissions():
    with TestClient(app) as client:
        for path in ("/api/v1/metadata", "/api/v1/dashboard", "/api/v1/review-tasks", "/api/v1/companies/A/analysis"):
            assert client.get(path).status_code == 401
        company = login(client)
        bank = login(client, "bank_demo")
        assert len(client.get("/api/v1/metadata", headers=company).json()["companies"]) == 1
        assert client.get("/api/v1/companies/B/analysis", headers=company).status_code == 403
        assert client.get("/api/v1/dashboard", headers=company).status_code == 403
        company_analysis=client.get("/api/v1/companies/A/analysis", headers=company).json()
        assert not {'network_graph','network_analysis','network','risk_paths','affected_credit_exposure'} & company_analysis.keys()
        assert client.post("/api/v1/enterprise/data-sync", json=sync_body(client, company), headers=bank).status_code == 403
        assert client.post("/api/v1/datasets/import", headers=bank, files={"file": ("x.json", b"{}")}).status_code == 403
        assert client.post("/api/v1/datasets/import", headers=company, files={"file": ("x.json", b"{}")}).status_code == 410
        assert client.post("/api/v1/auth/login", json={"account": "bank_demo", "password": "wrong", "role": "银行端"}).status_code == 401
        assert client.post("/api/v1/auth/login", json={"account": "bank_demo", "password": "错误密码", "role": "银行端"}).status_code == 401
        client.post("/api/v1/auth/logout", headers=company)
        assert client.get("/api/v1/enterprise/data-status", headers=company).status_code == 401
        assert client.get("/api/v1/dashboard", headers=bank).status_code == 200


def test_interface_persistence_idempotency_and_energy_case(isolated_platform, monkeypatch):
    with TestClient(app) as client:
        company, bank = login(client), login(client, "bank_demo")
        body = sync_body(client, company)
        original = isolated_platform.latest("A")
        response = client.post("/api/v1/enterprise/data-sync", json=body, headers=company)
        assert response.status_code == 200, response.text
        version = response.json()["version"]
        assert version["version"] == 2
        assert response.json()["replayed"] is False
        assert client.post("/api/v1/enterprise/data-sync", json=body, headers=company).json()["replayed"] is True
        assert isolated_platform.latest("A")["version"] == 2
        same_period = {**body, "request_id": str(uuid4()), "features": {**body["features"], "fund_usage_match": 1.0}}
        assert client.post("/api/v1/enterprise/data-sync", json=same_period, headers=company).status_code == 409
        modified = {**body, "features": {**body["features"], "project_progress": 0.5}}
        assert client.post("/api/v1/enterprise/data-sync", json=modified, headers=company).status_code == 409
        assert client.post("/api/v1/enterprise/data-sync", json={**body, "base_limit": 99999}, headers=company).status_code == 422
        assert BusinessStore(isolated_platform.path).latest("A")["id"] == version["id"]
        latest = isolated_platform.latest("A")
        def csv_must_not_be_reloaded():
            raise AssertionError("业务工作台应读取数据库")
        monkeypatch.setattr("services.business_store.load_demo_data", csv_must_not_be_reloaded)
        assert latest["payload"]["company"]["base_limit"] == original["payload"]["company"]["base_limit"]
        analysis = client.get("/api/v1/companies/A/analysis", headers=bank).json()
        assert analysis["data_version"]["version"] == 2
        assert analysis["transition_evidence"]["emissions"]["current_period"] == "2026-01"
        task = next(t for t in response.json()["tasks"] if t["kind"] == "energy_spike" and t["is_current"])
        task = submit(client, company, task)
        material = task["submissions"][-1]["materials"][0]
        assert client.get(f"/api/v1/materials/{material['id']}", headers=company).status_code == 200
        other = login(client, "company_B")
        assert client.get(f"/api/v1/materials/{material['id']}", headers=other).status_code == 403
        assert client.get(f"/api/v1/review-tasks/{task['id']}", headers=other).status_code == 403
        decision = {"revision": task["revision"], "action": "approve_reasonable", "comment": "检修证明与期间一致，核验通过并保留实际生产数据。"}
        assert client.post(f"/api/v1/review-tasks/{task['id']}/decision", json=decision, headers=company).status_code == 403
        reviewed = client.post(f"/api/v1/review-tasks/{task['id']}/decision", json=decision, headers=bank)
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["task"]["status"] == "resolved"
        impact = reviewed.json()["impact"]
        assert impact["before"] == impact["after"]  # Explanation does not erase real energy effects.
        assert isolated_platform.latest("A")["id"] == latest["id"]
        assert client.post(f"/api/v1/review-tasks/{task['id']}/decision", json=decision, headers=bank).status_code == 409


def test_model_case_quality_recalculation_scope_and_new_version():
    with TestClient(app) as client:
        company, bank = login(client), login(client, "bank_demo")
        body = sync_body(client, company, extreme=True)
        synced = client.post("/api/v1/enterprise/data-sync", json=body, headers=company).json()
        task = next(t for t in synced["tasks"] if t["kind"] == "data_anomaly" and t["is_current"])
        task = submit(client, company, task)
        stress_before = client.get("/api/v1/companies/A/analysis", headers=bank, params={"scenario": "天然气价格上涨30%"}).json()["company"]
        response = client.post(f"/api/v1/review-tasks/{task['id']}/decision", headers=bank, json={"revision": task["revision"], "action": "approve_reasonable", "comment": "核验当前组合数据及证明相符，限定当前版本解除质量扣减。"})
        assert response.status_code == 200, response.text
        before, after = response.json()["impact"].values()
        assert after["raw_anomaly_score"] == before["raw_anomaly_score"]
        assert after["data_quality"] == 0.9
        assert after["credibility"] > before["credibility"]
        assert after["effective_anomaly_score"] == 0
        assert after["p_target"] == before["p_target"]
        stress_after = client.get("/api/v1/companies/A/analysis", headers=bank, params={"scenario": "天然气价格上涨30%"}).json()["company"]
        assert stress_after["data_quality"] == stress_before["data_quality"]
        assert not stress_after["anomaly_reviewed"]
        assert any(t["kind"] == "energy_spike" and t["status"] == "awaiting_material" for t in client.get("/api/v1/review-tasks", headers=company).json()["items"])
        body["request_id"] = str(uuid4())
        body["reporting_period"] = "2026-02"
        client.post("/api/v1/enterprise/data-sync", json=body, headers=company)
        current = client.get("/api/v1/companies/A/analysis", headers=bank).json()["company"]
        assert not current["anomaly_reviewed"]
        assert current["effective_anomaly_score"] > 0


def test_return_resubmit_correction_recompute_and_audit(isolated_platform):
    isolated_platform.seed()
    prior = isolated_platform.latest('F')
    payload = json.loads(json.dumps(prior['payload']))
    payload['features']['fund_usage_match'] = .82
    with isolated_platform.connect() as db:
        isolated_platform._insert_version(db, 'F', payload, prior['period'], '测试资金用途偏离')
    with TestClient(app) as client:
        company, bank = login(client, "company_F"), login(client, "bank_demo")
        task = next(t for t in client.get("/api/v1/review-tasks", headers=company).json()["items"] if t["kind"] == "fund_usage")
        original = isolated_platform.latest("F")
        task = submit(client, company, task, {"features": {"fund_usage_match": 0.96}})
        assert isolated_platform.latest("F")["payload"]["features"]["fund_usage_match"] != 0.96
        returned = client.post(f"/api/v1/review-tasks/{task['id']}/decision", headers=bank, json={"revision": task["revision"], "action": "return", "comment": "请补充对应合同和付款核对信息。"})
        assert returned.status_code == 200
        task = submit(client, company, returned.json()["task"], {"features": {"fund_usage_match": 0.96}})
        corrected = client.post(f"/api/v1/review-tasks/{task['id']}/decision", headers=bank, json={"revision": task["revision"], "action": "approve_correction", "comment": "合同与付款核对一致，同意更正资金用途指标并重新测算。"})
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["task"]["outcome"] == "corrected"
        latest = isolated_platform.latest("F")
        assert latest["version"] == original["version"] + 1
        assert latest["payload"]["features"]["fund_usage_match"] == 0.96
        assert len(corrected.json()["task"]["submissions"]) == 2
        assert len(corrected.json()["task"]["history"]) == 4
        assert len(client.get(f"/api/v1/review-tasks/{task['id']}", headers=company).json()["submissions"]) == 2
        assert client.get("/api/v1/companies/F/analysis", headers=bank).json()["project"]["fund_usage_match"] == 0.96


def test_stale_materials_invalid_files_and_validation(isolated_platform):
    with TestClient(app) as client:
        company, bank = login(client, "company_F"), login(client, "bank_demo")
        task = client.get("/api/v1/review-tasks", headers=company).json()["items"][0]
        form = {"task_id": task["id"], "revision": task["revision"], "version_id": task["version_id"], "explanation": "说明和材料用于当前报告期间。"}
        for name, payload in [("伪造.pdf", b"<html>bad</html>"), ("程序.exe", b"bad"), ("过大.txt", b"a" * (10 * 1024 * 1024 + 1))]:
            assert client.post("/api/v1/enterprise/evidence", headers=company, data=form, files={"files": (name, payload)}).status_code == 400
        task = client.post("/api/v1/enterprise/evidence", headers=company, data=form).json()
        assert client.post(f"/api/v1/review-tasks/{task['id']}/decision", headers=bank, json={"revision": task["revision"], "action": "approve_reasonable", "comment": "附件不全也不能直接核验通过。"}).status_code == 400
        invalid = sync_body(client, company)
        invalid["energy_records"][0]["output"] = 0
        assert client.post("/api/v1/enterprise/data-sync", headers=company, json=invalid).status_code == 400
        valid = sync_body(client, company)
        client.post("/api/v1/enterprise/data-sync", headers=company, json=valid)
        assert client.post(f"/api/v1/review-tasks/{task['id']}/decision", headers=bank, json={"revision": task["revision"], "action": "track", "comment": "旧版本材料不能覆盖新数据。"}).status_code == 409
        assert client.post("/api/v1/enterprise/evidence", headers=company, data=form).status_code == 409


def test_process_facts_review_and_current_period_interface(isolated_platform):
    with TestClient(app) as client:
        company, bank = login(client), login(client, 'bank_demo')
        original = isolated_platform.latest('A')
        periods = sorted({row['period'] for row in original['payload']['energy']})
        routes = []
        for period, process in [(periods[0], 20), (periods[-1], 10)]:
            energy = [row for row in original['payload']['energy'] if row['period'] == period]
            routes.append(dict(period=period, route_id='原有路线', output=energy[0]['output'], process_emissions=process,
                               energy_records=[{key: row[key] for key in ('energy_type', 'energy', 'emission_factor')} for row in energy]))
        body = sync_body(client, company)
        assert client.post('/api/v1/enterprise/data-sync', headers=company, json={**body, 'route_records': routes}).status_code == 409
        form = {'version_id': original['id'], 'explanation': '补充基期与报告期非燃烧过程排放及工艺能耗明细，申请核验。', 'corrections': json.dumps({'route_records': routes})}
        submitted = client.post('/api/v1/enterprise/evidence', headers=company, data=form,
                                files={'files': ('工艺证明.txt', '工艺数据核验证明，仅测试。'.encode(), 'text/plain')})
        assert submitted.status_code == 200, submitted.text
        task = submitted.json()
        before = client.get('/api/v1/companies/A/analysis', headers=bank).json()
        assert before['lmdi']['process'] is None
        approved = client.post(f"/api/v1/review-tasks/{task['id']}/decision", headers=bank,
                               json={'revision': task['revision'], 'action': 'approve_correction', 'comment': '工艺产量、能耗与同期数据一致，核验通过。'})
        assert approved.status_code == 200, approved.text
        after = client.get('/api/v1/companies/A/analysis', headers=bank).json()
        assert after['lmdi']['process_available']
        assert after['lmdi']['base_emissions'] == pytest.approx(before['lmdi']['base_emissions'] + 20)
        assert after['lmdi']['current_emissions'] == pytest.approx(before['lmdi']['current_emissions'] + 10)
        assert abs(after['lmdi']['residual']) < 1e-7
        assert after['company']['p_target'] == before['company']['p_target']  # Existing model has no fabricated process feature.
        assert BusinessStore(isolated_platform.path).latest('A')['payload']['routes'] == routes
        assert 'routes' not in original['payload']
        # A new reporting period can supply matching route facts directly through the enterprise API.
        body = sync_body(client, company)
        route = {**routes[-1], 'period': body['reporting_period'], 'output': body['energy_records'][0]['output'],
                 'energy_records': [{key: row[key] for key in ('energy_type', 'energy', 'emission_factor')} for row in body['energy_records']]}
        invalid = {**route, 'process_emissions': -1}
        assert client.post('/api/v1/enterprise/data-sync', headers=company, json={**body, 'route_records': [invalid]}).status_code == 400
        assert isolated_platform.latest('A')['version'] == 2
        accepted = client.post('/api/v1/enterprise/data-sync', headers=company, json={**body, 'route_records': [route]})
        assert accepted.status_code == 200, accepted.text
        assert client.get('/api/v1/companies/A/analysis', headers=bank).json()['lmdi']['process_available']
        # A correction cannot silently invalidate route-energy reconciliation.
        broken = dict(body['energy_records'][0], energy=body['energy_records'][0]['energy'] * 2)
        latest = isolated_platform.latest('A')
        form['version_id'] = latest['id']
        form['corrections'] = json.dumps({'energy_records': [broken, *body['energy_records'][1:]]})
        assert client.post('/api/v1/enterprise/evidence', headers=company, data=form).status_code == 400
