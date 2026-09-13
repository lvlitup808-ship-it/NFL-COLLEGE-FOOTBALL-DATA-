import argparse
import asyncio
import json
from pathlib import Path

import pytest

from scripts.sunday_triage import (
    build_hard_fails,
    ingest_run_week_attribution,
    main,
    scan_ingest_tag_dml,
    stage,
    validate_return_object,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "agent" / "sunday-triage" / "40-returns.schema.json").read_text()
)


def pass_object():
    return {
        "season": 2025,
        "week": 1,
        "source": "cfbd",
        "n_plays": 20,
        "n_unknown_family": 20,
        "n_unknown_formation": 20,
        "n_missing_external_id": 0,
        "hard_fails": [],
        "report_path": "agent/sunday-triage/report.md",
        "verdict": "pass",
        "retry_reason": None,
    }


def test_return_schema_validates_pass_and_rejects_extra_keys():
    validate_return_object(pass_object(), SCHEMA)
    invalid = {**pass_object(), "approved": True}
    with pytest.raises(ValueError, match="extra=.*approved"):
        validate_return_object(invalid, SCHEMA)


def test_duplicate_external_id_is_a_hard_fail():
    failures = build_hard_fails(
        n_duplicate_external_id=2,
        n_source_family_promotions=0,
        n_ingest_tag_dml=0,
        ingest_runs=[{"status": "succeeded"}],
    )
    assert "duplicate_external_id: 2" in failures


def test_source_play_family_promotion_is_a_hard_fail():
    failures = build_hard_fails(
        n_duplicate_external_id=0,
        n_source_family_promotions=1,
        n_ingest_tag_dml=0,
        ingest_runs=[{"status": "succeeded"}],
    )
    assert "source_play_class_promoted_to_play_family: 1" in failures


def test_ingest_script_program_tag_dml_is_a_hard_fail(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "ingest_cfbd.py").write_text(
        "await conn.execute('INSERT INTO program_play_tags (play_id) VALUES ($1)')"
    )
    count = scan_ingest_tag_dml(tmp_path, "cfbd")
    failures = build_hard_fails(
        n_duplicate_external_id=0,
        n_source_family_promotions=0,
        n_ingest_tag_dml=count,
        ingest_runs=[{"status": "succeeded"}],
    )
    assert count == 1
    assert "trusted_tag_write_in_ingest_code: 1" in failures


def test_missing_ingest_week_does_not_invent_one_from_finished_at():
    metadata = {"batch_size": 500, "finished_at": "2025-09-07T22:00:00Z"}
    assert ingest_run_week_attribution(metadata, 2) is None
    assert ingest_run_week_attribution({"start_week": 1, "end_week": 3}, 2) is True


def test_runner_never_inserts_program_play_tags():
    source = (ROOT / "scripts" / "sunday_triage.py").read_text().upper()
    forbidden = "INSERT" + " INTO " + "PROGRAM_PLAY_TAGS"
    assert forbidden not in source


def test_current_ingest_scripts_do_not_write_program_play_tags():
    assert scan_ingest_tag_dml(ROOT) == 0


def test_exported_counts_stage_report_and_return_expected_exit_codes(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    triage_dir = tmp_path / "agent" / "sunday-triage"
    triage_dir.mkdir(parents=True)
    (triage_dir / "40-returns.schema.json").write_text(json.dumps(SCHEMA))
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "ingest_cfbd.py").write_text("# no trusted-tag DML\n")

    counts_path = tmp_path / "counts.json"
    counts = {
        "n_plays": 20,
        "n_unknown_family": 20,
        "n_unknown_formation": 20,
        "n_missing_external_id": 0,
        "n_duplicate_external_id": 0,
        "n_source_family_promotions": 0,
        "ingest_runs": [
            {
                "id": "run-1",
                "status": "succeeded",
                "rows_seen": 20,
                "rows_inserted": 20,
                "rows_updated": 0,
                "rows_skipped": 0,
                "error_count": 0,
                "metadata": {"batch_size": 20},
            }
        ],
    }
    counts_path.write_text(json.dumps(counts))
    args = argparse.Namespace(
        season=2025,
        week=1,
        source="cfbd",
        retry_count=0,
        database_url=None,
        counts_json=str(counts_path),
    )

    result, exit_code = asyncio.run(stage(args, tmp_path))
    report = (triage_dir / "report.md").read_text()
    assert exit_code == 0
    assert result["verdict"] == "pass"
    assert "ASSUMPTION: no live DB" in report
    assert "NOT IN THE EVIDENCE: ingest run week attribution" in report

    counts["n_duplicate_external_id"] = 1
    counts_path.write_text(json.dumps(counts))
    result, exit_code = asyncio.run(stage(args, tmp_path))
    assert exit_code == 2
    assert result["verdict"] == "fail"


def test_usage_error_returns_one(capsys):
    assert main([]) == 1
    assert "usage error:" in capsys.readouterr().err
