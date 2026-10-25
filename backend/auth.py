from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.business_store import business_store

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    account: str
    role: str
    company_id: str | None
    token_hash: str


def login(account: str, password: str, role: str):
    business_store.seed()
    if not hmac.compare_digest(password.encode(), os.getenv("PLATFORM_DEMO_PASSWORD", "demo123").encode()):
        raise HTTPException(401, "账号或密码不正确")
    company_id = None
    if account == "bank_demo":
        actual_role = "银行端"
    else:
        company_id = "A" if account == "company_demo" else account.removeprefix("company_") if account.startswith("company_") else ""
        try:
            business_store.latest(company_id)
        except KeyError:
            raise HTTPException(401, "账号或密码不正确")
        actual_role = "企业端"
    if actual_role != role:
        raise HTTPException(403, "账号与所选端口不匹配")
    token = secrets.token_urlsafe(40)
    expires_at = time.time() + 8 * 3600
    with business_store.connect() as db:
        db.execute("DELETE FROM business_sessions WHERE expires_at < ?", (time.time(),))
        db.execute("INSERT INTO business_sessions VALUES(?,?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), account, actual_role, company_id, expires_at))
    return {"token": token, "account": account, "role": actual_role, "company_id": company_id, "expires_at": expires_at}


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if credentials is None:
        raise HTTPException(401, "请先登录")
    digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    with business_store.connect() as db:
        row = db.execute("SELECT * FROM business_sessions WHERE token_hash=? AND expires_at>?", (digest, time.time())).fetchone()
    if not row:
        raise HTTPException(401, "登录已失效，请重新登录")
    return Principal(row["account"], row["role"], row["company_id"], digest)


def require_bank(user: Principal = Depends(current_user)) -> Principal:
    if user.role != "银行端":
        raise HTTPException(403, "仅银行审核人员可执行此操作")
    return user


def require_company(user: Principal = Depends(current_user)) -> Principal:
    if user.role != "企业端":
        raise HTTPException(403, "仅企业端可提交数据与材料")
    return user


def check_company(user: Principal, company_id: str):
    if user.role == "企业端" and user.company_id != company_id:
        raise HTTPException(403, "仅可访问本企业数据")
