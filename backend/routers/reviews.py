from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from backend.auth import Principal, check_company, current_user, login, require_bank, require_company
from services.analysis_service import get_analysis_service
from services.business_store import ConflictError, business_store

router = APIRouter(tags=["enterprise-data-and-reviews"])


class LoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)
    role: Literal["银行端", "企业端"]


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=100)
    source_system: str = Field(min_length=1, max_length=100)
    reporting_period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    features: dict[str, float] = Field(default_factory=dict)
    energy_records: list[dict] | None = Field(default=None, max_length=20)
    route_records: list[dict] | None = Field(default=None, max_length=400)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    action: Literal["approve_reasonable", "approve_correction", "return", "track"]
    comment: str = Field(min_length=5, max_length=4000)


def refresh_tasks():
    service = get_analysis_service()
    with service.lock, service.store.lock:
        service.refresh()


def translate_error(exc):
    if isinstance(exc, ConflictError):
        return HTTPException(409, str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(403, str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(404, str(exc))
    return HTTPException(400, str(exc))


@router.post("/auth/login")
def create_session(body: LoginRequest):
    return login(body.account.strip(), body.password, body.role)


@router.post("/auth/logout")
def logout(user: Principal = Depends(current_user)):
    with business_store.connect() as db:
        db.execute("DELETE FROM business_sessions WHERE token_hash=?", (user.token_hash,))
    return {"ok": True}


@router.get("/enterprise/data-status")
def data_status(user: Principal = Depends(require_company)):
    refresh_tasks()
    latest = business_store.latest(user.company_id)
    payload = latest.pop("payload")
    return {**latest, "company_name": payload["company"]["company_name"], "features": {key: payload["features"][key] for key in ("project_progress", "milestone_delay_days", "fund_usage_match", "own_fund_arrival", "cashflow_coverage", "energy_cost_ratio", "data_completeness")}, "energy_records": [{key: row[key] for key in ("energy_type", "energy", "output", "emission_factor")} for row in payload["energy"] if row["period"] == latest["period"]], "route_records": payload.get("routes", []), "record_count": len(payload["energy"])}


@router.post("/enterprise/data-sync")
def sync_data(body: SyncRequest, user: Principal = Depends(require_company)):
    service = get_analysis_service()
    try:
        with service.lock, business_store.lock:
            patch = body.model_dump(include={"features", "energy_records", "route_records"}, exclude_none=True)
            version, replayed = business_store.sync(user.company_id, body.request_id, body.source_system, body.reporting_period, patch)
            service.refresh()
            return {"version": {key: version[key] for key in ("id", "version", "period", "source", "created_at")}, "replayed": replayed, "tasks": business_store.tasks(user.company_id)}
    except (ValueError, KeyError) as exc:
        raise translate_error(exc) from exc


@router.get("/review-tasks")
def tasks(user: Principal = Depends(current_user)):
    refresh_tasks()
    return {"items": business_store.tasks(user.company_id if user.role == "企业端" else None)}


@router.get("/review-tasks/{task_id}")
def task_detail(task_id: str, user: Principal = Depends(current_user)):
    try:
        item = business_store.task(task_id)
        check_company(user, item["company_id"])
        return item
    except KeyError as exc:
        raise translate_error(exc) from exc


def checked_material(upload: UploadFile, content: bytes):
    name = (upload.filename or "材料").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if c.isprintable())[:150]
    suffix = Path(name).suffix.lower()
    mime = None
    if suffix == ".pdf" and content.startswith(b"%PDF-"):
        mime = "application/pdf"
    elif suffix == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif suffix in (".jpg", ".jpeg") and content.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif suffix == ".txt":
        try:
            content.decode("utf-8-sig")
            mime = "text/plain; charset=utf-8"
        except UnicodeDecodeError:
            pass
    if not content or len(content) > 10 * 1024 * 1024 or not mime:
        raise ValueError("材料需为 PDF、PNG、JPG 或 UTF-8 TXT，文件内容须与类型一致，单份不超过 10 MB")
    return {"name": name, "mime": mime, "content": content}


@router.post("/enterprise/evidence")
async def submit_evidence(
    explanation: str = Form(min_length=5, max_length=6000),
    version_id: int = Form(ge=1), task_id: str = Form(default=""), revision: int = Form(default=0),
    corrections: str = Form(default="{}", max_length=20000),
    files: list[UploadFile] = File(default=[]), user: Principal = Depends(require_company),
):
    try:
        if len(files) > 3:
            raise ValueError("每次最多提交 3 份材料")
        patch = json.loads(corrections)
        if not isinstance(patch, dict):
            raise ValueError("更正数据须为 JSON 对象")
        if len(explanation.strip()) < 5:
            raise ValueError("请填写至少 5 个字符的说明")
        materials = [checked_material(upload, await upload.read(10 * 1024 * 1024 + 1)) for upload in files]
        service = get_analysis_service()
        with service.lock, business_store.lock:
            return business_store.submit(user.company_id, user.account, task_id or None, revision, version_id, explanation.strip(), patch, materials)
    except (ValueError, KeyError, PermissionError) as exc:
        raise translate_error(exc) from exc
    finally:
        for upload in files:
            await upload.close()


def impact(payload):
    company = payload["company"]
    return {"data_version": payload["data_version"]["version"], "credibility": payload["transition_credibility"]["score"], "data_quality": company["data_quality"], "raw_anomaly_score": company["raw_anomaly_score"], "effective_anomaly_score": company["effective_anomaly_score"], "p_target": company["p_target"], "final_limit": company["final_limit"], "warning_level": company["warning_level"]}


@router.post("/review-tasks/{task_id}/decision")
def decide(task_id: str, body: ReviewRequest, user: Principal = Depends(require_bank)):
    service = get_analysis_service()
    try:
        if len(body.comment.strip()) < 5:
            raise ValueError("审核意见至少 5 个字符")
        with service.lock, business_store.lock:
            task = business_store.task(task_id)
            before = impact(service.company_analysis(task["company_id"], "正常情景"))
            event_id = business_store.review(task_id, user.account, body.revision, body.action, body.comment.strip(), before)
            after = impact(service.company_analysis(task["company_id"], "正常情景"))
            business_store.finish_review(event_id, after)
            return {"task": business_store.task(task_id), "impact": {"before": before, "after": after}}
    except (ValueError, KeyError) as exc:
        raise translate_error(exc) from exc


@router.get("/materials/{material_id}")
def material_content(material_id: str, user: Principal = Depends(current_user)):
    try:
        material = business_store.material(material_id)
        check_company(user, material["company_id"])
        return Response(material["content"], media_type=material["mime"], headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(material['name'])}", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox", "Cache-Control": "no-store"})
    except KeyError as exc:
        raise translate_error(exc) from exc
