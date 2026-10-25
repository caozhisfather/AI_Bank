from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from backend.auth import Principal, require_company
from fastapi.responses import FileResponse

router = APIRouter(tags=["datasets"])
TEMPLATE_FILE = Path(__file__).resolve().parents[2] / "data" / "templates" / "company_import_example.csv"
STRUCTURED_TEMPLATE_FILE = Path(__file__).resolve().parents[2] / "data" / "templates" / "structured_company_import_example.json"


@router.get("/datasets/template", response_class=FileResponse)
def download_template() -> FileResponse:
    return FileResponse(
        TEMPLATE_FILE,
        media_type="text/csv; charset=utf-8",
        filename="company_import_template.csv",
    )


@router.get("/datasets/structured-template", response_class=FileResponse)
def download_structured_template() -> FileResponse:
    return FileResponse(
        STRUCTURED_TEMPLATE_FILE,
        media_type="application/json; charset=utf-8",
        filename="six_table_import_template.json",
    )


@router.post("/datasets/import")
async def import_dataset(file: UploadFile = File(...), user: Principal = Depends(require_company)) -> dict:
    try:
        raise HTTPException(status_code=410, detail="业务数据已迁移至企业接口 /enterprise/data-sync；证明材料请使用 /enterprise/evidence")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()
