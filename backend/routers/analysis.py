from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from backend.auth import Principal, check_company, current_user, require_bank

from services.analysis_service import get_analysis_service
from services.live_workflow import list_runs, start_workflow

router = APIRouter(tags=["analysis"])


class AnalysisRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str = Field(default="正常情景", min_length=1, max_length=50)


@router.post("/companies/{company_id}/analysis-workflow")
def analysis_workflow(company_id: str, body: AnalysisRunRequest, user: Principal = Depends(require_bank)):
    try:
        stream = start_workflow(get_analysis_service().store, company_id, body.scenario)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="企业数据不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return StreamingResponse(stream, media_type="application/x-ndjson", headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no",
    })


@router.get("/companies/{company_id}/analysis-workflows")
def analysis_workflow_history(company_id: str, user: Principal = Depends(require_bank)) -> dict:
    return {"items": list_runs(get_analysis_service().store, company_id)}


@router.get("/metadata")
def metadata(user: Principal = Depends(current_user)) -> dict:
    result = get_analysis_service().metadata()
    if user.role == "企业端":
        result["companies"] = [row for row in result["companies"] if row["company_id"] == user.company_id]
    return result


@router.get("/dashboard")
def dashboard(scenario: str = Query(default="正常情景"), user: Principal = Depends(require_bank)) -> dict:
    try:
        return get_analysis_service().dashboard(scenario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/companies/{company_id}/analysis")
def company_analysis(
    company_id: str,
    scenario: str = Query(default="正常情景"),
    user: Principal = Depends(current_user),
) -> dict:
    check_company(user, company_id)
    try:
        result = get_analysis_service().company_analysis(company_id, scenario)
        if user.role == "企业端":
            for key in ("network", "network_graph", "network_analysis", "risk_paths", "affected_credit_exposure"):
                result.pop(key, None)
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/companies/{company_id}/agent-workflow")
def agent_workflow(
    company_id: str,
    scenario: str = Query(default="正常情景"),
    user: Principal = Depends(require_bank),
) -> dict:
    try:
        return get_analysis_service().workflow(company_id, scenario)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
