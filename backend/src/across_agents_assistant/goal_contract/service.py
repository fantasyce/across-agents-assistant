from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping, Sequence

from ..approval.receipts import ApprovalReceiptError, verify_approval_receipt_purpose
from ..persistence.goal_contract_store import GoalContractStoreError
from ..persistence.service import PersistenceService
from .models import GoalProjectionFacts
from .projector import project_goal_state


class GoalContractService:
    """Host-governed Goal operations shared by API and Direct Agent mode."""

    def __init__(self, persistence: PersistenceService):
        self.persistence = persistence
        self.store = persistence.goal_contracts

    def get_goal(self, task_id: str) -> dict[str, Any]:
        contract = self.store.get_current(task_id)
        if contract is None:
            raise KeyError(task_id)
        evidence = self.store.list_evidence(contract["goal_id"], contract["revision"])
        criterion_evidence: dict[str, str] = {}
        for binding in evidence:
            state = str(binding.get("trust_state") or "unverified")
            verdict = "verified" if state == "verified" and binding.get("verdict") == "verified" else state
            if state in {"invalid", "failed"}:
                verdict = "failed"
            for criterion_id_value in binding.get("criterion_ids") or []:
                prior = criterion_evidence.get(criterion_id_value)
                criterion_evidence[criterion_id_value] = _stronger_evidence_state(prior, verdict)
        pending = self.store.list_pending_proposals(contract["goal_id"], contract["revision"])
        facts = GoalProjectionFacts(
            contract=contract,
            dependencies={},
            criterion_evidence=criterion_evidence,
            reviews={},
            pending_decisions=tuple(item["proposal_id"] for item in pending),
            active_lease_count=0,
            execution_state="finished",
        )
        return {
            "contract": contract,
            "projection": project_goal_state(facts),
            "pending_proposals": pending,
            "evidence_bindings": evidence,
        }

    def save_proposal(
        self,
        *,
        task_id: str,
        proposal: Mapping[str, Any],
        expected_revision: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        contract = self._current(task_id, expected_revision)
        if proposal.get("goal_id") != contract["goal_id"] or proposal.get("base_goal_revision") != expected_revision:
            raise GoalContractStoreError("goal_revision_conflict", "proposal base revision does not match current goal")
        return self.store.save_proposal(proposal, idempotency_key=idempotency_key)

    def decide_proposal(
        self,
        *,
        task_id: str,
        proposal_id: str,
        decision: str,
        expected_revision: int,
        operation_indexes: Sequence[int] = (),
        approver_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        selected_indexes = _selected_operation_indexes(proposal, decision, operation_indexes)
        replay = self.store.get_proposal_decision_replay(proposal_id, idempotency_key)
        if replay is not None:
            if replay["decision_state"] != decision:
                raise GoalContractStoreError(
                    "goal_idempotency_conflict",
                    "proposal decision idempotency key was reused with another decision",
                )
            current = self.store.get_current(task_id)
            if current is None:
                raise KeyError(task_id)
            result_revision = expected_revision + 1 if decision in {"accepted", "partially_accepted"} else expected_revision
            subject_payload = _decision_subject(
                proposal_id=proposal_id,
                goal_id=proposal["goal_id"],
                base_revision=expected_revision,
                result_revision=result_revision,
                decision=decision,
                selected_indexes=selected_indexes,
            )
            try:
                verify_approval_receipt_purpose(
                    replay["decision_receipt"],
                    expected_purpose="goal_change_decision",
                    subject_type="goal_change_proposal",
                    subject_id=f"{proposal_id}:{expected_revision}:{decision}",
                    subject_payload=subject_payload,
                )
            except ApprovalReceiptError as exc:
                raise GoalContractStoreError(
                    "goal_idempotency_conflict", "proposal decision replay does not match the original request"
                ) from exc
            return {
                "proposal": replay,
                "contract": current,
                "decision_receipt": replay["decision_receipt"],
                "projection": self.get_goal(task_id)["projection"],
            }

        current = self._current(task_id, expected_revision)
        if proposal["goal_id"] != current["goal_id"] or proposal["base_goal_revision"] != expected_revision:
            raise GoalContractStoreError("goal_revision_conflict", "proposal is stale for the current goal")
        if approver_id == proposal.get("proposed_by") or not (
            approver_id.startswith("human:") or approver_id.startswith("local-human")
        ):
            raise GoalContractStoreError("goal_decision_unauthorized", "goal decisions require a host human approver")

        resulting_contract = current
        if decision in {"accepted", "partially_accepted"}:
            resulting_contract = _materialize_revision(
                current,
                proposal,
                selected_indexes=selected_indexes,
                approver_id=approver_id,
            )
            resulting_contract = self.store.create_revision(
                resulting_contract,
                expected_revision=expected_revision,
                idempotency_key=f"{idempotency_key}:goal-revision",
            )

        receipt_subject = _decision_subject(
            proposal_id=proposal_id,
            goal_id=current["goal_id"],
            base_revision=expected_revision,
            result_revision=resulting_contract["revision"],
            decision=decision,
            selected_indexes=selected_indexes,
        )
        receipt = self.persistence.record_approval_receipt(
            subject_type="goal_change_proposal",
            subject_id=f"{proposal_id}:{expected_revision}:{decision}",
            subject_payload=receipt_subject,
            scope="goal_change_decision",
            purpose="goal_change_decision",
            decision="approved" if decision in {"accepted", "partially_accepted"} else "rejected",
            proposer_id=str(proposal.get("proposed_by") or "unknown-proposer"),
            approver_id=approver_id,
            risk_level=str((proposal.get("risk_summary") or {}).get("level") or "unknown"),
            idempotency_key=f"{idempotency_key}:decision-receipt",
        )
        decided = self.store.decide_proposal(
            proposal_id,
            decision=decision,
            expected_revision=expected_revision,
            decision_receipt=receipt,
            idempotency_key=idempotency_key,
        )
        return {
            "proposal": decided,
            "contract": resulting_contract,
            "decision_receipt": receipt,
            "projection": self.get_goal(task_id)["projection"],
        }

    def record_direct_evidence(
        self,
        *,
        task_id: str,
        goal_revision: int,
        criterion_ids: Sequence[str],
        artifact_digests: Mapping[str, str],
        validator_id: str,
        verdict: str,
        input_fingerprint: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        contract = self._current(task_id, goal_revision)
        allowed = {item["criterion_id"] for item in contract["acceptance_criteria"]}
        selected = sorted(set(str(item) for item in criterion_ids))
        if not selected or not set(selected).issubset(allowed):
            raise GoalContractStoreError("goal_criterion_invalid", "direct evidence criterion binding is invalid")
        if verdict != "verified":
            raise GoalContractStoreError("goal_evidence_untrusted", "direct evidence requires a trusted validator verdict")
        request = {
            "task_id": task_id,
            "goal_revision": goal_revision,
            "criterion_ids": selected,
            "artifact_digests": dict(sorted(artifact_digests.items())),
            "validator_id": validator_id,
            "verdict": verdict,
            "input_fingerprint": input_fingerprint,
        }
        digest = _digest(request)
        binding = {
            "schema_version": "across-goal-evidence-binding/1.0",
            "evidence_id": f"evidence-{digest[:24]}",
            "goal_id": contract["goal_id"],
            "goal_revision": goal_revision,
            "task_id": task_id,
            "criterion_ids": selected,
            "run_id": f"direct-run-{digest[:16]}",
            "attempt_id": f"direct-attempt-{digest[16:32]}",
            "executor": "aaa-direct-agent",
            "artifact_digests": request["artifact_digests"],
            "input_fingerprint": input_fingerprint,
            "validator": {"validator_id": validator_id, "authority": "aaa-host"},
            "verdict": verdict,
            "trust_state": "verified",
        }
        return self.store.save_evidence(binding, idempotency_key=idempotency_key)

    def request_revalidation(
        self,
        *,
        task_id: str,
        expected_revision: int,
        criterion_ids: Sequence[str],
        reason: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        contract = self._current(task_id, expected_revision)
        selected = sorted(set(str(item) for item in criterion_ids))
        allowed = {item["criterion_id"] for item in contract["acceptance_criteria"]}
        if not selected or not set(selected).issubset(allowed):
            raise GoalContractStoreError("goal_criterion_invalid", "revalidation criterion binding is invalid")
        material = {
            "goal_id": contract["goal_id"],
            "revision": expected_revision,
            "criterion_ids": selected,
            "reason": str(reason).strip(),
        }
        digest = _digest(material)
        event = {
            "schema_version": "across-goal-revalidation-request/1.0",
            "invalidation_id": f"invalidation-{digest[:24]}",
            "goal_id": contract["goal_id"],
            "from_revision": expected_revision,
            "to_revision": None,
            "criterion_ids": selected,
            "reason": material["reason"],
            "state": "pending",
        }
        return self.store.save_invalidation(event, idempotency_key=idempotency_key)

    def _current(self, task_id: str, expected_revision: int) -> dict[str, Any]:
        contract = self.store.get_current(task_id)
        if contract is None:
            raise KeyError(task_id)
        if contract["revision"] != expected_revision:
            raise GoalContractStoreError(
                "goal_revision_conflict",
                f"expected_revision {expected_revision} does not match current revision {contract['revision']}",
            )
        return contract


def _selected_operation_indexes(
    proposal: Mapping[str, Any], decision: str, operation_indexes: Sequence[int]
) -> list[int]:
    operations = list(proposal.get("operations") or [])
    if decision == "accepted":
        return list(range(len(operations)))
    if decision == "partially_accepted":
        selected = sorted(set(int(index) for index in operation_indexes))
        if not selected or any(index < 0 or index >= len(operations) for index in selected):
            raise GoalContractStoreError("goal_partial_decision_invalid", "partial acceptance requires valid operation indexes")
        return selected
    if decision in {"rejected", "superseded"}:
        return []
    raise GoalContractStoreError("goal_decision_invalid", "proposal decision is invalid")


def _decision_subject(
    *,
    proposal_id: str,
    goal_id: str,
    base_revision: int,
    result_revision: int,
    decision: str,
    selected_indexes: Sequence[int],
) -> dict[str, Any]:
    return {
        "proposal_id": proposal_id,
        "goal_id": goal_id,
        "base_goal_revision": base_revision,
        "result_goal_revision": result_revision,
        "decision": decision,
        "operation_indexes": list(selected_indexes),
    }


def _materialize_revision(
    current: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    selected_indexes: Sequence[int],
    approver_id: str,
) -> dict[str, Any]:
    candidate = copy.deepcopy(dict(current))
    operations = list(proposal.get("operations") or [])
    for index in selected_indexes:
        _apply_operation(candidate, operations[index])
    candidate["revision"] = int(current["revision"]) + 1
    candidate["source"] = "api"
    candidate["confirmed_by"] = approver_id
    candidate["confirmed_at"] = proposal["created_at"]
    candidate["created_at"] = proposal["created_at"]
    return candidate


def _apply_operation(document: dict[str, Any], operation: Mapping[str, Any]) -> None:
    tokens = [_unescape_pointer(item) for item in str(operation["path"]).split("/")[1:]]
    if not tokens:
        raise GoalContractStoreError("goal_operation_invalid", "proposal cannot replace the goal root")
    parent: Any = document
    for token in tokens[:-1]:
        parent = parent[int(token)] if isinstance(parent, list) else parent[token]
    leaf = tokens[-1]
    op = operation["op"]
    if isinstance(parent, list):
        if op == "add" and leaf == "-":
            parent.append(copy.deepcopy(operation["value"]))
        elif op == "remove":
            parent.pop(int(leaf))
        else:
            parent[int(leaf)] = copy.deepcopy(operation["value"])
    elif op == "remove":
        parent.pop(leaf)
    else:
        parent[leaf] = copy.deepcopy(operation["value"])


def _unescape_pointer(value: str) -> str:
    return value.replace("~1", "/").replace("~0", "~")


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stronger_evidence_state(current: str | None, candidate: str) -> str:
    order = {"failed": 5, "invalid": 5, "stale": 4, "verified": 3, "unverified": 2, "missing": 1}
    return candidate if order.get(candidate, 0) >= order.get(current or "", 0) else str(current)
