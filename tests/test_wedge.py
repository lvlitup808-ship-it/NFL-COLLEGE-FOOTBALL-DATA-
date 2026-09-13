import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.wedge import AuthContext, BulkTagBody, VOCAB, require_coach, require_write


def test_controlled_vocabulary_is_locked_and_bounded():
    assert sum(len(values) for values in VOCAB.values()) == 40
    assert "pass" not in VOCAB["play_family"]
    assert "run" not in VOCAB["play_family"]
    assert "UNKNOWN" in VOCAB["play_family"]


def test_required_vocab_groups_exist():
    assert set(VOCAB) == {
        "play_family",
        "formation",
        "motion",
        "coverage_family",
        "personnel",
    }


def test_unknown_is_available_for_every_group():
    assert all("UNKNOWN" in values for values in VOCAB.values())


def context(role: str) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(), email="staff@example.edu", program_id=uuid.uuid4(),
        program_name="Pilot", role=role,
    )


def test_viewer_reads_but_cannot_write_and_ga_cannot_resolve():
    with pytest.raises(HTTPException) as viewer_error:
        require_write(context("viewer"))
    assert viewer_error.value.status_code == 403
    require_write(context("ga"))
    with pytest.raises(HTTPException) as ga_error:
        require_coach(context("ga"))
    assert ga_error.value.detail == "coach_role_required"
    require_coach(context("coach"))


def test_bulk_tag_is_bounded_to_40_plays_and_uses_tag_body():
    body = BulkTagBody.model_validate(
        {"play_ids": [str(uuid.uuid4())], "tags": {"formation": "UNKNOWN"}}
    )
    assert body.tags.formation == "UNKNOWN"
    with pytest.raises(ValidationError):
        BulkTagBody.model_validate(
            {"play_ids": [str(uuid.uuid4()) for _ in range(41)], "tags": {"formation": "2X2"}}
        )
