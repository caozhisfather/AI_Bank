from fastapi import APIRouter, HTTPException, Query

from services.analysis_service import get_analysis_service

router = APIRouter(tags=["analysis"])


@router.get("/metadata")
def metadata() -> dict:
    return get_analysis_service().metadata()


@router.get("/dashboard")
def dashboard(scenario: str = Query(default="正常情景")) -> dict:
    try:
        return get_analysis_service().dashboard(scenario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/companies/{company_id}/analysis")
def company_analysis(
    company_id: str,
    scenario: str = Query(default="正常情景"),
) -> dict:
    try:
        return get_analysis_service().company_analysis(company_id, scenario)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
