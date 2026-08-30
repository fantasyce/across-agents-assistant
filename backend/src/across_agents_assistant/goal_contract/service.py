from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping, Sequence

from ..approval.receipts import ApprovalReceiptError, verify_approval_receipt_purpose
from ..persistence.goal_contract_store import GoalContractStoreError
from ..persistence.service import PersistenceService
from .models import GoalProjectionFacts
from .protocol import stable_goal_hash
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
        invalidations = self.store.list_invalidations(contract["goal_id"], contract["revision"])
        stale_criteria = {
            str(criterion_id)
            for invalidation in invalidations
            if invalidation.get("state") == "pending"
            for criterion_id in invalidation.get("criterion_ids") or []
        }
        criterion_evidence: dict[str, str] = {}
        for binding in evidence:
            state = str(binding.get("trust_state") or "unverified")
            verdict = "verified" if state == "verified" and binding.get("verdict") == "verified" else state
            if state in {"invalid", "failed"}:
                verdict = "failed"
            for criterion_id_value in binding.get("criterion_ids") or []:
                prior = criterion_evidence.get(criterion_id_value)
                criterion_evidence[criterion_id_value] = _stronger_evidence_state(prior, verdict)
        for criterion_id_value in stale_criteria:
            if criterion_id_value in criterion_evidence:
                criterion_evidence[criterion_id_value] = "stale"
        pending = self.store.list_pending_proposals(contract["goal_id"], contract["revision"])
        reviews = self.store.list_reviews(contract["goal_id"], contract["revision"])
        review_states: dict[str, str] = {}
        for review in reviews:
            for criterion_id_value in review.get("criterion_ids") or ():
                review_states[str(criterion_id_value)] = str(review.get("status") or "pending")
        facts = GoalProjectionFacts(
            contract=contract,
            dependencies={},
            criterion_evidence=criterion_evidence,
            reviews=review_states,
            pending_decisions=tuple(item["proposal_id"] for item in pending),
            active_lease_count=0,
            execution_state="finished",
        )
        projection = project_goal_state(facts)
        return {
            "contract": contract,
            "projection": projection,
            "pending_proposals": pending,
            "evidence_bindings": evidence,
            "invalidations": invalidations,
            "reviews": reviews,
            "available_actions": _available_goal_actions(
                contract=contract,
                projection=projection,
                evidence=evidence,
                invalidations=invalidations,
                reviews=reviews,
            ),
        }

    def authorize_execution_contract(self, claimed: Mapping[str, Any]) -> dict[str, Any]:
        """Bind execution only to AAA's current, human-confirmed Goal revision."""
        if not isinstance(claimed, Mapping):
            raise GoalContractStoreError(
                "goal_execution_contract_not_authoritative", "Goal execution contract must be an object"
            )
        required_fields = {
            "schema_version", "goal_id", "goal_revision", "task_id", "criterion_ids", "input_fingerprint"
        }
        if set(claimed) != required_fields:
            raise GoalContractStoreError(
                "goal_execution_contract_not_authoritative", "Goal execution contract fields do not match the host contract"
            )
        task_id = claimed.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise GoalContractStoreError(
                "goal_execution_contract_not_authoritative", "Goal execution contract task_id is invalid"
            )
        current = self.store.get_current(task_id.strip())
        if current is None or not current.get("confirmed_by") or not current.get("confirmed_at"):
            raise GoalContractStoreError(
                "goal_execution_contract_not_authoritative", "No current human-confirmed Goal revision exists for this task"
            )
        executable_criteria = sorted(
            str(criterion["criterion_id"])
            for criterion in current.get("acceptance_criteria") or ()
            if criterion.get("required") is True
        )
        if not executable_criteria:
            raise GoalContractStoreError(
                "goal_execution_contract_not_authoritative", "The current Goal has no host-authorized executable criteria"
            )
        expected = {
            "schema_version": "across-goal-execution-contract/1.0",
            "goal_id": current["goal_id"],
            "goal_revision": current["revision"],
            "task_id": current["task_id"],
            "criterion_ids": executable_criteria,
            "input_fingerprint": stable_goal_hash(current),
        }
        normalized_claim = dict(claimed)
        criteria = normalized_claim.get("criterion_ids")
        if not isinstance(criteria, list) or any(not isinstance(item, str) for item in criteria):
            raise GoalContractStoreError(
                "goal_execution_contract_not_authoritative", "Goal execution contract criteria are invalid"
            )
        normalized_claim["criterion_ids"] = sorted(criteria)
        if type(normalized_claim.get("goal_revision")) is not int or normalized_claim != expected:
            raise GoalContractStoreError(
                "goal_execution_contract_not_authoritative", "Goal execution contract does not match the current host revision"
            )
        return expected

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
            prior_evidence = self.store.list_evidence(current["goal_id"], expected_revision)
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
            self._carry_forward_evidence(
                prior_evidence,
                resulting_contract=resulting_contract,
                idempotency_key=idempotency_key,
            )
            impact = dict(proposal.get("impact_summary") or {})
            impacted_criteria = sorted({
                str(item)
                for item in impact.get("criterion_ids") or ()
                if str(item) in {criterion["criterion_id"] for criterion in resulting_contract["acceptance_criteria"]}
            })
            if impact.get("requires_revalidation") and impacted_criteria:
                material = {
                    "goal_id": resulting_contract["goal_id"],
                    "revision": resulting_contract["revision"],
                    "criterion_ids": impacted_criteria,
                    "proposal_id": proposal_id,
                }
                digest = _digest(material)
                self.store.save_invalidation(
                    {
                        "schema_version": "across-goal-revalidation-request/1.0",
                        "invalidation_id": f"invalidation-{digest[:24]}",
                        "goal_id": resulting_contract["goal_id"],
                        "from_revision": resulting_contract["revision"],
                        "to_revision": None,
                        "criterion_ids": impacted_criteria,
                        "reason": str(proposal.get("reason") or "Goal revision changed"),
                        "state": "pending",
                    },
                    idempotency_key=f"{idempotency_key}:revision-invalidation",
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
        attempt_id: str | None = None,
        supersedes_evidence_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        selected = sorted(set(str(item) for item in criterion_ids))
        if len(selected) != 1:
            raise GoalContractStoreError(
                "goal_criterion_invalid", "execution evidence must bind exactly one criterion"
            )
        direct_identity = _digest(
            {
                "task_id": task_id,
                "goal_revision": goal_revision,
                "criterion_id": selected[0],
                "artifact_digests": dict(artifact_digests),
                "input_fingerprint": input_fingerprint,
            }
        )
        return self.record_execution_evidence(
            task_id=task_id,
            goal_revision=goal_revision,
            criterion_id=selected[0],
            artifact_digests=artifact_digests,
            executor="aaa-direct-agent",
            run_id=f"direct-run-{direct_identity[:16]}",
            attempt_id=attempt_id or f"direct-attempt-{direct_identity[16:32]}",
            validator_id=validator_id,
            validator_authority="aaa-host",
            verdict=verdict,
            input_fingerprint=input_fingerprint,
            receipt_hash=None,
            supersedes_evidence_ids=supersedes_evidence_ids,
            idempotency_key=idempotency_key,
        )

    def record_execution_evidence(
        self,
        *,
        task_id: str,
        goal_revision: int,
        criterion_id: str,
        artifact_digests: Mapping[str, str],
        executor: str,
        run_id: str,
        attempt_id: str,
        validator_id: str,
        validator_authority: str,
        verdict: str,
        input_fingerprint: str,
        receipt_hash: str | None,
        idempotency_key: str,
        supersedes_evidence_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        contract = self._current(task_id, goal_revision)
        allowed = {str(item["criterion_id"]) for item in contract["acceptance_criteria"]}
        normalized_criterion = str(criterion_id or "").strip()
        if normalized_criterion not in allowed:
            raise GoalContractStoreError("goal_criterion_invalid", "execution evidence criterion binding is invalid")
        normalized_artifacts = dict(sorted((str(key), str(value).lower()) for key, value in artifact_digests.items()))
        if not normalized_artifacts or any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in normalized_artifacts.values()
        ):
            raise GoalContractStoreError("goal_evidence_untrusted", "execution evidence artifact digests are invalid")
        if verdict != "verified" or validator_authority not in {"aaa-host", "across-orchestrator", "across-worker"}:
            raise GoalContractStoreError("goal_evidence_untrusted", "execution evidence requires trusted validator authority")
        normalized_executor = str(executor or "").strip()
        normalized_validator = str(validator_id or "").strip()
        normalized_input = str(input_fingerprint or "").lower()
        if not normalized_executor or not normalized_validator or len(normalized_input) != 64:
            raise GoalContractStoreError("goal_evidence_untrusted", "execution evidence identity is incomplete")
        normalized_receipt = str(receipt_hash or "").lower() or None
        if normalized_receipt is not None and (
            len(normalized_receipt) != 64
            or any(character not in "0123456789abcdef" for character in normalized_receipt)
        ):
            raise GoalContractStoreError("goal_evidence_untrusted", "execution evidence receipt hash is invalid")
        request = {
            "task_id": task_id,
            "goal_revision": goal_revision,
            "criterion_id": normalized_criterion,
            "artifact_digests": normalized_artifacts,
            "executor": normalized_executor,
            "run_id": str(run_id or "").strip(),
            "attempt_id": str(attempt_id or "").strip(),
            "validator_id": normalized_validator,
            "validator_authority": validator_authority,
            "verdict": verdict,
            "input_fingerprint": normalized_input,
            "receipt_hash": normalized_receipt,
            "supersedes_evidence_ids": sorted(set(map(str, supersedes_evidence_ids))),
        }
        digest = _digest(request)
        normalized_run = request["run_id"] or f"execution-run-{digest[:16]}"
        normalized_attempt = request["attempt_id"] or f"execution-attempt-{digest[16:32]}"
        binding = {
            "schema_version": "across-goal-evidence-binding/1.1",
            "evidence_id": f"evidence-{digest[:24]}",
            "goal_id": contract["goal_id"],
            "goal_revision": goal_revision,
            "task_id": task_id,
            "criterion_ids": [normalized_criterion],
            "run_id": normalized_run,
            "attempt_id": normalized_attempt,
            "executor": normalized_executor,
            "artifact_digests": normalized_artifacts,
            "input_fingerprint": normalized_input,
            "validator": {"validator_id": normalized_validator, "authority": validator_authority},
            "verdict": verdict,
            "trust_state": "verified",
        }
        if normalized_receipt:
            binding["receipt_hash"] = normalized_receipt
        if request["supersedes_evidence_ids"]:
            binding["supersedes_evidence_ids"] = request["supersedes_evidence_ids"]
        return self.store.save_evidence(binding, idempotency_key=idempotency_key)

    def record_result_review(
        self,
        *,
        task_id: str,
        expected_revision: int,
        decision: str,
        reason: str,
        reviewer_id: str,
        basis_evidence_ids: Sequence[str],
        attempt_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        contract = self._current(task_id, expected_revision)
        if decision not in {"passed", "rejected"}:
            raise GoalContractStoreError("goal_review_invalid", "result review decision is invalid")
        if not (reviewer_id.startswith("human:") or reviewer_id.startswith("local-human")):
            raise GoalContractStoreError("goal_review_unauthorized", "result review requires a host human")
        review_criteria = [
            str(item["criterion_id"])
            for item in contract["acceptance_criteria"]
            if item.get("required", True) and item.get("review_policy") != "automatic"
        ]
        required_criteria = {
            str(item["criterion_id"])
            for item in contract["acceptance_criteria"]
            if item.get("required", True)
        }
        evidence_by_id = {
            str(item["evidence_id"]): item
            for item in self.store.list_evidence(contract["goal_id"], expected_revision)
        }
        selected_ids = sorted(set(map(str, basis_evidence_ids)))
        selected = [evidence_by_id[item] for item in selected_ids if item in evidence_by_id]
        normalized_attempt = str(attempt_id or "").strip()
        superseded_ids = {
            str(evidence_id)
            for item in evidence_by_id.values()
            for evidence_id in item.get("supersedes_evidence_ids") or ()
        }
        if len(selected) != len(selected_ids) or any(
            item.get("trust_state") != "verified"
            or item.get("verdict") != "verified"
            or item.get("attempt_id") != normalized_attempt
            or item.get("evidence_id") in superseded_ids
            for item in selected
        ):
            raise GoalContractStoreError("goal_evidence_missing", "result review evidence is not current and verified")
        covered = {
            str(criterion_id)
            for item in selected
            for criterion_id in item.get("criterion_ids") or ()
        }
        if decision == "passed" and (not normalized_attempt or not required_criteria.issubset(covered)):
            raise GoalContractStoreError("goal_evidence_missing", "result review requires verified execution evidence")
        if decision == "passed":
            stale_criteria = {
                str(criterion_id)
                for invalidation in self.store.list_invalidations(contract["goal_id"], expected_revision)
                if invalidation.get("state") == "pending"
                for criterion_id in invalidation.get("criterion_ids") or ()
            }
            if required_criteria.intersection(stale_criteria):
                raise GoalContractStoreError("goal_evidence_missing", "result review evidence requires revalidation")
        prior_reviews = self.store.list_reviews(contract["goal_id"], expected_revision)
        if (
            decision == "passed"
            and prior_reviews
            and prior_reviews[-1].get("status") == "rejected"
            and prior_reviews[-1].get("attempt_id") == normalized_attempt
        ):
            raise GoalContractStoreError(
                "goal_repair_required", "a rejected Attempt must be replaced before it can pass review"
            )
        material = {
            "goal_id": contract["goal_id"],
            "goal_revision": expected_revision,
            "task_id": task_id,
            "criterion_ids": review_criteria,
            "decision": decision,
            "reason": str(reason or "").strip(),
            "reviewer_id": reviewer_id,
            "basis_evidence_ids": selected_ids,
            "attempt_id": normalized_attempt,
        }
        digest = _digest(material)
        receipt = self.persistence.record_approval_receipt(
            subject_type="goal_result",
            subject_id=f"{contract['goal_id']}:{expected_revision}:{digest[:16]}",
            subject_payload=material,
            scope="goal_result_review",
            purpose="goal_result_review",
            decision="approved" if decision == "passed" else "rejected",
            proposer_id="goal-execution-validator",
            approver_id=reviewer_id,
            risk_level="medium",
            idempotency_key=f"{idempotency_key}:receipt",
        )
        review = self.store.save_review(
            {
                "schema_version": "across-goal-result-review/1.1",
                "review_id": f"goal-review-{digest[:24]}",
                "goal_id": contract["goal_id"],
                "goal_revision": expected_revision,
                "criterion_ids": review_criteria,
                "status": decision,
                "reason": material["reason"],
                "reviewer_id": reviewer_id,
                "basis_evidence_ids": selected_ids,
                "attempt_id": normalized_attempt,
                "decision_receipt": receipt,
            },
            idempotency_key=idempotency_key,
        )
        return {"review": review, "projection": self.get_goal(task_id)["projection"]}

    def record_criterion_review(
        self,
        *,
        task_id: str,
        expected_revision: int,
        criterion_id: str,
        decision: str,
        reason: str,
        reviewer_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        contract = self._current(task_id, expected_revision)
        criterion = next(
            (item for item in contract["acceptance_criteria"] if item["criterion_id"] == criterion_id),
            None,
        )
        if criterion is None:
            raise GoalContractStoreError("goal_criterion_invalid", "review criterion is invalid")
        if criterion.get("review_policy") == "automatic":
            raise GoalContractStoreError("goal_review_not_required", "automatic criteria do not accept human review")
        if decision not in {"passed", "rejected"}:
            raise GoalContractStoreError("goal_review_invalid", "review decision is invalid")
        if not (reviewer_id.startswith("human:") or reviewer_id.startswith("local-human")):
            raise GoalContractStoreError("goal_review_unauthorized", "criterion review requires a host human")
        material = {
            "goal_id": contract["goal_id"],
            "goal_revision": expected_revision,
            "criterion_id": criterion_id,
            "decision": decision,
            "reason": str(reason).strip(),
            "reviewer_id": reviewer_id,
        }
        digest = _digest(material)
        receipt = self.persistence.record_approval_receipt(
            subject_type="goal_criterion",
            subject_id=f"{contract['goal_id']}:{expected_revision}:{criterion_id}:{digest[:12]}",
            subject_payload=material,
            scope="goal_criterion_review",
            purpose="goal_criterion_review",
            decision="approved" if decision == "passed" else "rejected",
            proposer_id="goal-validator",
            approver_id=reviewer_id,
            risk_level="medium",
            idempotency_key=f"{idempotency_key}:receipt",
        )
        review = self.store.save_review(
            {
                "schema_version": "across-goal-criterion-review/1.0",
                "review_id": f"goal-review-{digest[:24]}",
                "goal_id": contract["goal_id"],
                "goal_revision": expected_revision,
                "criterion_ids": [criterion_id],
                "status": decision,
                "reason": material["reason"],
                "reviewer_id": reviewer_id,
                "decision_receipt": receipt,
            },
            idempotency_key=idempotency_key,
        )
        return {"review": review, "projection": self.get_goal(task_id)["projection"]}

    def complete_revalidation(
        self,
        *,
        task_id: str,
        expected_revision: int,
        criterion_ids: Sequence[str],
        artifact_digests: Mapping[str, str],
        validator_id: str,
        verdict: str,
        input_fingerprint: str,
        attempt: Mapping[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        contract = self._current(task_id, expected_revision)
        selected = sorted(set(map(str, criterion_ids)))
        pending = [
            item for item in self.store.list_invalidations(contract["goal_id"], expected_revision)
            if item.get("state") == "pending"
            and set(map(str, item.get("criterion_ids") or ())).issubset(selected)
        ]
        if not pending:
            raise GoalContractStoreError("goal_revalidation_missing", "no matching pending invalidation exists")
        normalized_attempt = dict(attempt)
        if normalized_attempt.get("schema_version") != "across-goal-revalidation-attempt/1.1":
            raise GoalContractStoreError("goal_revalidation_invalid", "revalidation attempt schema is invalid")
        if normalized_attempt.get("state") != "completed":
            raise GoalContractStoreError("goal_revalidation_invalid", "revalidation attempt is not completed")
        if (
            normalized_attempt.get("goal_id") != contract["goal_id"]
            or int(normalized_attempt.get("goal_revision") or 0) != expected_revision
            or normalized_attempt.get("task_id") != task_id
        ):
            raise GoalContractStoreError("goal_revalidation_invalid", "revalidation attempt authority does not match")
        if sorted(set(map(str, normalized_attempt.get("criterion_ids") or ()))) != selected:
            raise GoalContractStoreError("goal_revalidation_invalid", "revalidation attempt criteria do not match")
        attempt_id = str(normalized_attempt.get("attempt_id") or "").strip()
        if not attempt_id:
            raise GoalContractStoreError("goal_revalidation_invalid", "revalidation attempt id is required")
        superseded = sorted({
            evidence_id
            for item in pending
            for evidence_id in normalized_attempt.get("supersedes_evidence_ids") or ()
        }) or sorted({
            binding["evidence_id"]
            for binding in self.store.list_evidence(contract["goal_id"], expected_revision)
            if set(binding.get("criterion_ids") or ()).intersection(selected)
        })
        executor = "aaa-direct-agent" if contract.get("execution_profile") == "direct" else "across-orchestrator"
        bindings = [
            self.record_execution_evidence(
                task_id=task_id,
                goal_revision=expected_revision,
                criterion_id=criterion_id,
                artifact_digests=artifact_digests,
                executor=executor,
                run_id=str(normalized_attempt.get("run_id") or f"revalidation-run-{attempt_id}"),
                attempt_id=attempt_id,
                validator_id=validator_id,
                validator_authority="aaa-host",
                verdict=verdict,
                input_fingerprint=input_fingerprint,
                receipt_hash=str(normalized_attempt.get("evidence_receipt_hash") or "") or None,
                supersedes_evidence_ids=superseded,
                idempotency_key=f"{idempotency_key}:evidence:{criterion_id}",
            )
            for criterion_id in selected
        ]
        normalized_attempt["replacement_evidence_ids"] = [item["evidence_id"] for item in bindings]
        completed = self.store.complete_invalidations(
            goal_id=contract["goal_id"],
            revision=expected_revision,
            criterion_ids=selected,
            attempt=normalized_attempt,
            evidence_ids=normalized_attempt["replacement_evidence_ids"],
            completion_idempotency_key=idempotency_key,
        )
        return {
            "attempt": normalized_attempt,
            "invalidation": completed[0],
            "completed_invalidations": completed,
            "evidence_binding": bindings[0],
            "evidence_bindings": bindings,
            "projection": self.get_goal(task_id)["projection"],
        }

    def completed_revalidation_replay(
        self, *, task_id: str, expected_revision: int, idempotency_key: str
    ) -> dict[str, Any] | None:
        contract = self._current(task_id, expected_revision)
        for invalidation in self.store.list_invalidations(contract["goal_id"], expected_revision):
            if (
                invalidation.get("state") == "completed"
                and invalidation.get("completion_idempotency_key") == idempotency_key
            ):
                envelope = self.get_goal(task_id)
                replacement_ids = set(map(str, invalidation.get("replacement_evidence_ids") or ()))
                binding = next(
                    (item for item in envelope["evidence_bindings"] if item.get("evidence_id") in replacement_ids),
                    None,
                )
                bindings = [
                    item for item in envelope["evidence_bindings"]
                    if item.get("evidence_id") in replacement_ids
                ]
                return {
                    "attempt": invalidation.get("attempt"),
                    "invalidation": invalidation,
                    "completed_invalidations": [invalidation],
                    "evidence_binding": binding,
                    "evidence_bindings": bindings,
                    "projection": envelope["projection"],
                }
        return None

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
        for existing in self.store.list_invalidations(contract["goal_id"], expected_revision):
            if existing.get("state") == "pending" and sorted(existing.get("criterion_ids") or ()) == selected:
                return existing
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

    def revalidation_attempt_payload(
        self,
        *,
        task_id: str,
        expected_revision: int,
        criterion_ids: Sequence[str],
    ) -> dict[str, Any]:
        contract = self._current(task_id, expected_revision)
        selected = sorted(set(map(str, criterion_ids)))
        evidence = self.store.list_evidence(contract["goal_id"], expected_revision)
        changed = [f"criterion:{criterion_id}:revision:{expected_revision}" for criterion_id in selected]
        criteria: dict[str, Any] = {}
        for criterion in contract["acceptance_criteria"]:
            criterion_id = str(criterion["criterion_id"])
            criteria[criterion_id] = {
                "input_fingerprints": [
                    f"criterion:{criterion_id}:revision:{expected_revision}"
                ],
                "depends_on": [],
                "evidence_ids": [
                    item["evidence_id"]
                    for item in evidence
                    if criterion_id in set(map(str, item.get("criterion_ids") or ()))
                ],
            }
        authority = {
            "goal_id": contract["goal_id"],
            "goal_revision": expected_revision,
            "task_id": task_id,
            "criterion_ids": selected,
            "changed_fingerprints": changed,
        }
        return {
            "schema_version": "across-goal-revalidation-request/1.1",
            "graph": {"criteria": criteria},
            **authority,
            "input_fingerprint": _digest(authority),
            "prior_attempt_number": sum(
                1
                for item in self.store.list_invalidations(contract["goal_id"], expected_revision)
                if item.get("attempt")
            ),
        }

    def attach_revalidation_attempt(
        self,
        *,
        task_id: str,
        expected_revision: int,
        criterion_ids: Sequence[str],
        attempt: Mapping[str, Any],
    ) -> dict[str, Any]:
        contract = self._current(task_id, expected_revision)
        selected = sorted(set(map(str, criterion_ids)))
        normalized = dict(attempt)
        if normalized.get("schema_version") != "across-goal-revalidation-attempt/1.1":
            raise GoalContractStoreError("goal_revalidation_invalid", "revalidation attempt schema is invalid")
        if normalized.get("state") not in {"awaiting_host_evidence", "queued", "running"}:
            raise GoalContractStoreError("goal_revalidation_invalid", "revalidation attempt is not active")
        if (
            normalized.get("goal_id") != contract["goal_id"]
            or int(normalized.get("goal_revision") or 0) != expected_revision
            or normalized.get("task_id") != task_id
            or sorted(set(map(str, normalized.get("criterion_ids") or ()))) != selected
        ):
            raise GoalContractStoreError("goal_revalidation_invalid", "revalidation attempt authority does not match")
        attached = self.store.attach_revalidation_attempt(
            goal_id=contract["goal_id"],
            revision=expected_revision,
            criterion_ids=selected,
            attempt=normalized,
        )
        return attached[0]

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

    def _carry_forward_evidence(
        self,
        evidence: Sequence[Mapping[str, Any]],
        *,
        resulting_contract: Mapping[str, Any],
        idempotency_key: str,
    ) -> None:
        allowed = {item["criterion_id"] for item in resulting_contract["acceptance_criteria"]}
        for index, original in enumerate(evidence):
            selected = sorted(set(map(str, original.get("criterion_ids") or ())).intersection(allowed))
            if not selected:
                continue
            payload = copy.deepcopy(dict(original))
            source_id = str(payload["evidence_id"])
            payload["goal_revision"] = int(resulting_contract["revision"])
            payload["criterion_ids"] = selected
            payload["reused_from_evidence_id"] = source_id
            payload["evidence_id"] = f"evidence-{_digest({'source': source_id, 'revision': resulting_contract['revision']})[:24]}"
            self.store.save_evidence(payload, idempotency_key=f"{idempotency_key}:reuse:{index}")


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


def _available_goal_actions(
    *,
    contract: Mapping[str, Any],
    projection: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    invalidations: Sequence[Mapping[str, Any]],
    reviews: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    required = {
        str(item["criterion_id"])
        for item in contract.get("acceptance_criteria") or ()
        if item.get("required", True)
    }
    stale = {
        str(criterion_id)
        for invalidation in invalidations
        if invalidation.get("state") == "pending"
        for criterion_id in invalidation.get("criterion_ids") or ()
    }
    superseded = {
        str(evidence_id)
        for binding in evidence
        for evidence_id in binding.get("supersedes_evidence_ids") or ()
    }
    selected: dict[str, Mapping[str, Any]] = {}
    for binding in reversed(evidence):
        if (
            binding.get("trust_state") != "verified"
            or binding.get("verdict") != "verified"
            or binding.get("evidence_id") in superseded
        ):
            continue
        for criterion_id in binding.get("criterion_ids") or ():
            normalized = str(criterion_id)
            if normalized in required and normalized not in stale:
                selected.setdefault(normalized, binding)
    attempts = {str(item.get("attempt_id") or "") for item in selected.values() if item.get("attempt_id")}
    evidence_ready = set(selected) == required and len(attempts) == 1
    current_attempt = next(iter(attempts), "")
    result_reviews = [item for item in reviews if item.get("schema_version") == "across-goal-result-review/1.1"]
    latest_review = result_reviews[-1] if result_reviews else None
    rejected_current_attempt = bool(
        latest_review
        and latest_review.get("status") == "rejected"
        and latest_review.get("attempt_id") == current_attempt
    )
    complete = bool(projection.get("is_complete"))

    if complete:
        accept_reason = "goal_already_complete"
    elif stale:
        accept_reason = "goal_revalidation_required"
    elif rejected_current_attempt:
        accept_reason = "goal_repair_required"
    elif not evidence_ready:
        accept_reason = "goal_evidence_missing" if len(attempts) <= 1 else "goal_evidence_conflict"
    else:
        accept_reason = None
    accept_enabled = accept_reason is None

    reject_enabled = not complete and not rejected_current_attempt
    reject_reason = None if reject_enabled else (
        "goal_already_complete" if complete else "goal_repair_required"
    )
    revalidate_enabled = bool(stale or rejected_current_attempt)
    return [
        {
            "action_id": "accept_result",
            "enabled": accept_enabled,
            "disabled_reason_code": accept_reason,
        },
        {
            "action_id": "reject_result",
            "enabled": reject_enabled,
            "disabled_reason_code": reject_reason,
        },
        {
            "action_id": "revalidate",
            "enabled": revalidate_enabled,
            "disabled_reason_code": None if revalidate_enabled else "goal_revalidation_not_required",
        },
    ]


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stronger_evidence_state(current: str | None, candidate: str) -> str:
    order = {"failed": 5, "invalid": 5, "stale": 4, "verified": 3, "unverified": 2, "missing": 1}
    return candidate if order.get(candidate, 0) >= order.get(current or "", 0) else str(current)
