from services.analysis_service import AnalysisService


def test_agent_workflow_is_auditable_and_scenario_aware():
    service = AnalysisService()
    normal = service.workflow("A", "正常情景")
    stress = service.workflow("A", "天然气价格上涨30%")
    assert normal["status"] == "completed"
    assert normal["workflow_id"].startswith("WF-")
    assert len(normal["steps"]) == 5
    assert stress["steps"][2]["status"] == "warning"
    assert "自动批贷" in stress["audit"]["boundary"]
