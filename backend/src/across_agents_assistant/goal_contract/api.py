from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..persistence.goal_contract_store import GoalContractStoreError
from ..persistence.service import PersistenceService
from .service import GoalContractService


class GoalProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal: dict[str, Any]
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=500)


class GoalProposalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    expected_revision: int = Field(ge=1)
    operation_indexes: list[int] = Field(default_factory=list)
    approver_id: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=500)


class GoalRevalidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    criterion_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=1, max_length=500)


def install_goal_contract_routes(
    app: FastAPI,
    *,
    service_provider: Callable[[], PersistenceService],
) -> None:
    router = APIRouter()

    def goals() -> GoalContractService:
        return GoalContractService(service_provider())

    @router.get("/api/tasks/{task_id}/goal")
    async def get_goal(task_id: str):
        return _translate(lambda: goals().get_goal(task_id))

    @router.post("/api/tasks/{task_id}/goal/proposals")
    async def save_goal_proposal(task_id: str, request: GoalProposalRequest):
        return _translate(
            lambda: goals().save_proposal(
                task_id=task_id,
                proposal=request.proposal,
                expected_revision=request.expected_revision,
                idempotency_key=request.idempotency_key,
            )
        )

    @router.post("/api/tasks/{task_id}/goal/proposals/{proposal_id}/decision")
    async def decide_goal_proposal(
        task_id: str, proposal_id: str, request: GoalProposalDecisionRequest
    ):
        return _translate(
            lambda: goals().decide_proposal(
                task_id=task_id,
                proposal_id=proposal_id,
                decision=request.decision,
                expected_revision=request.expected_revision,
                operation_indexes=request.operation_indexes,
                approver_id=request.approver_id,
                idempotency_key=request.idempotency_key,
            )
        )

    @router.post("/api/tasks/{task_id}/goal/revalidate")
    async def revalidate_goal(task_id: str, request: GoalRevalidationRequest):
        return _translate(
            lambda: goals().request_revalidation(
                task_id=task_id,
                expected_revision=request.expected_revision,
                criterion_ids=request.criterion_ids,
                reason=request.reason,
                idempotency_key=request.idempotency_key,
            )
        )

    app.include_router(router)


def _translate(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Goal resource not found") from exc
    except GoalContractStoreError as exc:
        status = 409 if exc.code in {
            "goal_revision_conflict",
            "goal_idempotency_conflict",
            "goal_proposal_conflict",
            "goal_proposal_already_decided",
        } else 422
        raise HTTPException(
            status_code=status,
            detail={"reason_code": exc.code, "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"reason_code": "goal_request_invalid", "message": str(exc)},
        ) from exc
