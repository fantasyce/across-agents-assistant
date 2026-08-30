import copy
import json
from pathlib import Path

import pytest

from across_agents_assistant.goal_contract.protocol import (
    criterion_id,
    normalize_goal_change_proposal,
    normalize_goal_contract,
    stable_goal_hash,
)


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "goal-contract"
EXPECTED_GOAL_HASH = "2d6996c43ab0104c3b94f87a2b6030d2d6bab0df1fca777bebba894b21fe83a8"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_criterion_ids_are_cross_language_stable():
    assert criterion_id("All required tests pass.", "test_suite") == "criterion-36bc8486dd50ddc0"
    assert criterion_id("  All   required tests pass.  ", "TEST_SUITE") == "criterion-36bc8486dd50ddc0"


def test_goal_hash_uses_canonical_object_keys_without_reordering_arrays():
    fixture = load_fixture("simple.json")
    reversed_keys = dict(reversed(list(fixture.items())))

    assert stable_goal_hash(fixture) == EXPECTED_GOAL_HASH
    assert stable_goal_hash(reversed_keys) == EXPECTED_GOAL_HASH

    reversed_criteria = copy.deepcopy(fixture)
    reversed_criteria["acceptance_criteria"].reverse()
    assert stable_goal_hash(reversed_criteria) != EXPECTED_GOAL_HASH


def test_goal_hash_accepts_only_cross_runtime_safe_integers():
    with pytest.raises(ValueError, match="integer|canonical JSON"):
        stable_goal_hash({"value": 1e-7})
    assert stable_goal_hash({"value": 1.0}) == stable_goal_hash({"value": 1})
    assert stable_goal_hash({"value": -0.0}) == stable_goal_hash({"value": 0})


def test_goal_contract_normalization_preserves_the_confirmed_fixture():
    fixture = load_fixture("simple.json")
    assert normalize_goal_contract(fixture) == fixture


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(revision=0), "revision"),
        (lambda value: value.pop("statement"), "statement"),
        (lambda value: value.update(schema_version="across-goal-contract/2.0"), "schema_version"),
        (
            lambda value: value["acceptance_criteria"].append(copy.deepcopy(value["acceptance_criteria"][0])),
            "criterion_id",
        ),
    ],
)
def test_goal_contract_rejects_invalid_mutations(mutation, message):
    fixture = load_fixture("simple.json")
    mutation(fixture)
    with pytest.raises(ValueError, match=message):
        normalize_goal_contract(fixture)


def test_goal_change_proposal_is_pending_and_base_revision_bound():
    fixture = load_fixture("change-proposal.json")
    assert normalize_goal_change_proposal(fixture) == fixture

    invalid_operation = copy.deepcopy(fixture)
    invalid_operation["operations"][0]["op"] = "confirm"
    with pytest.raises(ValueError, match="operation"):
        normalize_goal_change_proposal(invalid_operation)

    invalid_revision = copy.deepcopy(fixture)
    invalid_revision["base_goal_revision"] = 0
    with pytest.raises(ValueError, match="base_goal_revision"):
        normalize_goal_change_proposal(invalid_revision)

    nested_host_field = copy.deepcopy(fixture)
    nested_host_field["operations"][0]["path"] = "/confirmed_by/agent"
    with pytest.raises(ValueError, match="host-owned"):
        normalize_goal_change_proposal(nested_host_field)
