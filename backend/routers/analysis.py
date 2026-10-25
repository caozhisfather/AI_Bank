from fastapi import APIRouter, Depends, HTTPException, Query
from backend.auth import Principal, check_company, current_user, require_bank

from services.analysis_service import get_analysis_service

router = APIRouter(tags=["analysis"])


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
