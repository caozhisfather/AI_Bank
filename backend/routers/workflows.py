import os
from collections import OrderedDict
from importlib.util import find_spec
from threading import RLock
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from backend.auth import require_bank
from pydantic import BaseModel, ConfigDict, Field

from services.dataset_service import dataset_store
from services.imported_agent_workflow import run_imported_workflow
from services.persistent_store import persistent_store

router = APIRouter(tags=["agent-workflows"], dependencies=[Depends(require_bank)])
MAX_WORKFLOW_RUNS = 100
_workflow_runs: OrderedDict[str, dict[str, Any]] = OrderedDict()
_workflow_lock = RLock()


class WorkflowOptions(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)

    industry: str = Field(default="自动识别", max_length=50)
    scenario: str = Field(default="正常情景", max_length=50)
    support_ratio: float = Field(default=0.80, ge=0, le=1.5)
    propagation_decay: float = Field(default=0.55, ge=0, le=1)
    algorithm_params: dict[str, float] = Field(default_factory=dict)
    enabled_agents: list[str] = Field(default_factory=list, max_length=10)
    agent_mode: Literal["offline", "deterministic", "deepagent", "deepagents", "online"] = "offline"


class WorkflowRequest(BaseModel):
    dataset_id: str = Field(min_length=3, max_length=64)
    industry: str = Field(default="自动识别", max_length=50)
    scenario: str = Field(default="正常情景", max_length=50)
    transition_support_ratio: float = Field(default=0.20, ge=0, le=1.5)
    propagation_decay: float = Field(default=0.55, ge=0, le=1)
    network_risk_weight: float = Field(default=0.30, ge=0, le=1)
    execution_mode: Literal["offline", "deepagents"] = "offline"
    enabled_agents: list[str] = Field(
        default_factory=lambda: ["data", "transition", "park_risk", "finance", "compliance"],
        max_length=10,
    )
    options: WorkflowOptions | None = None

    def normalized_options(self) -> dict[str, Any]:
        if self.options is not None:
            return self.options.model_dump()
        return {
            "industry": self.industry,
            "scenario": self.scenario,
            "support_ratio": self.transition_support_ratio,
            "propagation_decay": self.propagation_decay,
            "algorithm_params": {"network_risk_factor": self.network_risk_weight},
            "enabled_agents": self.enabled_agents,
            "agent_mode": self.execution_mode,
        }


@router.post("/agent-workflows/run")
def run_workflow(request: WorkflowRequest) -> dict[str, Any]:
    try:
        dataset = dataset_store.get(request.dataset_id)
        result = run_imported_workflow(dataset, request.normalized_options())
        with _workflow_lock:
            _workflow_runs[result["workflow"]["workflow_id"]] = result
            while len(_workflow_runs) > MAX_WORKFLOW_RUNS:
                _workflow_runs.popitem(last=False)
        persistent_store.save_workflow(result["workflow"]["workflow_id"], result, keep=MAX_WORKFLOW_RUNS)
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/agent-workflows/capabilities")
def workflow_capabilities() -> dict[str, Any]:
    deepagents_installed = find_spec("deepagents") is not None
    deepagents_configured = bool(os.getenv("DEEPAGENT_MODEL") and os.getenv("OPENAI_API_KEY"))
    return {
        "orchestrator": "langgraph",
        "tool_framework": "langchain",
        "deepagents": {
            "installed": deepagents_installed,
            "configured": deepagents_configured,
            "default_mode": "deepagents" if deepagents_configured else "offline",
        },
        "human_review_required": True,
    }


@router.get("/agent-workflows")
def list_workflows(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 100))
    values = persistent_store.list_workflows(safe_limit)
    return {
        "items": [
            {
                "workflow_id": item["workflow"]["workflow_id"],
                "created_at": item["workflow"]["created_at"],
                "dataset_id": item["workflow"]["dataset_id"],
                "status": item["workflow"]["status"],
                "scenario": item["analysis"]["scenario"],
                "industry": item["analysis"]["industry"],
                "agent_mode": item["agent_mode"],
            }
            for item in values
        ]
    }


@router.get("/agent-workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> dict[str, Any]:
    with _workflow_lock:
        result = _workflow_runs.get(workflow_id)
    if result is None:
        result = persistent_store.get_workflow(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail="工作流记录不存在")
    return result
