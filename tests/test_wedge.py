from app.wedge import VOCAB


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
