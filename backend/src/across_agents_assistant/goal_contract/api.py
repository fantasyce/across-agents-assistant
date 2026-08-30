from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..persistence.goal_contract_store import GoalContractStoreError
from ..persistence.service import PersistenceService
from ..plugin_runtime import (
    PluginLifecycleError,
    build_direct_goal_revalidation_attempt,
    run_managed_goal_contract_probe,
    run_managed_goal_revalidation_complete,
    run_managed_goal_revalidation_plan,
    run_managed_goal_revalidation_start,
)
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


class GoalCriterionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    criterion_id: str = Field(min_length=1, max_length=500)
    decision: str
    reason: str = Field(min_length=1, max_length=2000)
    reviewer_id: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=500)


class GoalPluginProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract: dict[str, Any] | None = None
    allow_missing: bool = False


def install_goal_contract_routes(
    app: FastAPI,
    *,
    service_provider: Callable[[], PersistenceService],
    revalidation_verifier: Callable[[str, int, list[str], dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
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
        service = goals()
        replay = _translate(
            lambda: service.completed_revalidation_replay(
                task_id=task_id,
                expected_revision=request.expected_revision,
                idempotency_key=request.idempotency_key,
            )
        )
        if replay is not None:
            return replay
        pending = _translate(
            lambda: service.request_revalidation(
                task_id=task_id,
                expected_revision=request.expected_revision,
                criterion_ids=request.criterion_ids,
                reason=request.reason,
                idempotency_key=request.idempotency_key,
            )
        )
        if revalidation_verifier is None:
            return pending
        if pending.get("state") == "completed":
            envelope = service.get_goal(task_id)
            replacement_ids = set(map(str, pending.get("replacement_evidence_ids") or ()))
            evidence_binding = next(
                (item for item in envelope["evidence_bindings"] if item.get("evidence_id") in replacement_ids),
                None,
            )
            return {
                "attempt": pending.get("attempt"),
                "invalidation": pending,
                "completed_invalidations": [pending],
                "evidence_binding": evidence_binding,
                "projection": envelope["projection"],
            }
        try:
            attempt_payload = service.revalidation_attempt_payload(
                task_id=task_id,
                expected_revision=request.expected_revision,
                criterion_ids=request.criterion_ids,
            )
            provider_managed = True
            try:
                plan = await asyncio.to_thread(run_managed_goal_revalidation_plan, attempt_payload)
                attempt = await asyncio.to_thread(
                    run_managed_goal_revalidation_start,
                    {
                        **attempt_payload,
                        "execution_mode": "host_validation",
                        "idempotency_key": f"{request.idempotency_key}:provider-start",
                        "plan_hash": plan["plan_hash"],
                    },
                )
            except PluginLifecycleError:
                contract = service.get_goal(task_id)["contract"]
                if contract.get("execution_profile") != "direct":
                    raise
                provider_managed = False
                attempt = build_direct_goal_revalidation_attempt(
                    {**attempt_payload, "idempotency_key": f"{request.idempotency_key}:direct-start"}
                )
            service.attach_revalidation_attempt(
                task_id=task_id,
                expected_revision=request.expected_revision,
                criterion_ids=request.criterion_ids,
                attempt=attempt,
            )
            material = await revalidation_verifier(
                task_id,
                request.expected_revision,
                request.criterion_ids,
                attempt,
            )
            if provider_managed:
                receipt = _host_validation_receipt(attempt, material)
                attempt = await asyncio.to_thread(
                    run_managed_goal_revalidation_complete,
                    {"attempt_id": attempt["attempt_id"], "receipt": receipt},
                )
            else:
                attempt = {**attempt, "state": "completed"}
            return service.complete_revalidation(
                task_id=task_id,
                expected_revision=request.expected_revision,
                criterion_ids=request.criterion_ids,
                artifact_digests=material["artifact_digests"],
                validator_id=material["validator_id"],
                verdict=material["verdict"],
                input_fingerprint=material["input_fingerprint"],
                attempt=attempt,
                idempotency_key=request.idempotency_key,
            )
        except (KeyError, ValueError, GoalContractStoreError) as exc:
            return _translate(lambda: (_ for _ in ()).throw(exc))
        except PluginLifecycleError as exc:
            raise HTTPException(
                status_code=503,
                detail={"reason_code": "goal_revalidation_runtime_unavailable", "message": str(exc)},
            ) from exc

    @router.post("/api/tasks/{task_id}/goal/reviews")
    async def review_goal_criterion(task_id: str, request: GoalCriterionReviewRequest):
        return _translate(
            lambda: goals().record_criterion_review(
                task_id=task_id,
                expected_revision=request.expected_revision,
                criterion_id=request.criterion_id,
                decision=request.decision,
                reason=request.reason,
                reviewer_id=request.reviewer_id,
                idempotency_key=request.idempotency_key,
            )
        )

    @router.post("/api/goal-contract/plugin-probe")
    async def probe_goal_contract_plugins(request: GoalPluginProbeRequest):
        try:
            return await asyncio.to_thread(
                run_managed_goal_contract_probe,
                request.contract,
                allow_missing=request.allow_missing,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"reason_code": "goal_request_invalid", "message": str(exc)},
            ) from exc

    app.include_router(router)


def _host_validation_receipt(attempt: dict[str, Any], material: dict[str, Any]) -> dict[str, Any]:
    unsigned = {
        "schema_version": "across-goal-host-validation-evidence/1.1",
        "attempt_id": attempt["attempt_id"],
        "goal_id": attempt["goal_id"],
        "goal_revision": attempt["goal_revision"],
        "task_id": attempt["task_id"],
        "criterion_ids": attempt["criterion_ids"],
        "artifact_digests": material["artifact_digests"],
        "input_fingerprint": attempt["input_fingerprint"],
        "validator_id": material["validator_id"],
        "verdict": material["verdict"],
    }
    canonical = json.dumps(unsigned, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return {**unsigned, "receipt_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


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
