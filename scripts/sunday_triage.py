"""Stage a manual Sunday source-triage report for one season/week/source."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "agent" / "sunday-triage" / "report.md"
SCHEMA_PATH = ROOT / "agent" / "sunday-triage" / "40-returns.schema.json"

INGEST_DML_PATTERN = re.compile(
    r"\b(?:insert\s+into|update|delete\s+from)\s+program_play_tags\b",
    re.IGNORECASE | re.DOTALL,
)

PLAY_COUNTS_SQL = """
SELECT
  COUNT(*)::int AS n_plays,
  COUNT(*) FILTER (WHERE UPPER(COALESCE(p.play_family, 'UNKNOWN')) = 'UNKNOWN')::int
    AS n_unknown_family,
  COUNT(*) FILTER (WHERE UPPER(COALESCE(p.formation, 'UNKNOWN')) = 'UNKNOWN')::int
    AS n_unknown_formation,
  COUNT(*) FILTER (WHERE NULLIF(BTRIM(p.external_id), '') IS NULL)::int
    AS n_missing_external_id
FROM plays p
JOIN games g ON g.id = p.game_id
WHERE g.season = $1 AND g.week = $2 AND p.external_source = $3
"""

DUPLICATE_IDS_SQL = """
SELECT COUNT(*)::int
FROM (
  SELECT p.external_id
  FROM plays p
  JOIN games g ON g.id = p.game_id
  WHERE g.season = $1
    AND g.week = $2
    AND p.external_source = $3
    AND NULLIF(BTRIM(p.external_id), '') IS NOT NULL
  GROUP BY p.external_id
  HAVING COUNT(*) > 1
) duplicate_ids
"""

SOURCE_FAMILY_PROMOTIONS_SQL = """
SELECT COUNT(*)::int
FROM plays p
JOIN games g ON g.id = p.game_id
WHERE g.season = $1
  AND g.week = $2
  AND p.external_source = $3
  AND LOWER(p.play_family) IN ('pass', 'run')
"""

INGEST_RUNS_SQL = """
SELECT
  id::text AS id,
  source,
  season,
  status,
  rows_seen,
  rows_inserted,
  rows_updated,
  rows_skipped,
  error_count,
  metadata
FROM ingest_runs
WHERE season = $1
  AND source = $2
  AND status IN ('succeeded', 'failed')
ORDER BY started_at DESC
"""


class UsageError(ValueError):
    """Raised when a manual invocation cannot produce evidenced counts."""


class OneExitArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError(message)


def parser() -> argparse.ArgumentParser:
    result = OneExitArgumentParser(description=__doc__)
    result.add_argument("--season", required=True, type=int)
    result.add_argument("--week", required=True, type=int)
    result.add_argument("--source", required=True, choices=("cfbd", "nflverse"))
    result.add_argument("--retry-count", type=int, default=0)
    result.add_argument("--database-url")
    result.add_argument(
        "--counts-json",
        help="Path to an exported-counts JSON object when no database URL is available",
    )
    return result


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _non_negative_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if not _is_int(value) or value < 0:
        raise UsageError(f"{key} must be a non-negative integer")
    return value


def load_exported_counts(path: str, season: int, source: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"cannot read --counts-json: {exc}") from exc
    if not isinstance(payload, dict):
        raise UsageError("--counts-json must contain a JSON object")
    if "season" in payload and payload["season"] != season:
        raise UsageError("exported season does not match --season")
    if "source" in payload and payload["source"] != source:
        raise UsageError("exported source does not match --source")

    counts = {
        key: _non_negative_int(payload, key)
        for key in (
            "n_plays",
            "n_unknown_family",
            "n_unknown_formation",
            "n_missing_external_id",
            "n_duplicate_external_id",
            "n_source_family_promotions",
        )
    }
    ingest_runs = payload.get("ingest_runs")
    if not isinstance(ingest_runs, list) or any(not isinstance(row, dict) for row in ingest_runs):
        raise UsageError("ingest_runs must be an array of summary objects")
    counts["ingest_runs"] = ingest_runs
    retry_reason = payload.get("retry_reason")
    if retry_reason is not None and (not isinstance(retry_reason, str) or not retry_reason.strip()):
        raise UsageError("retry_reason must be null or a non-empty string")
    counts["retry_reason"] = retry_reason
    return counts


def ingest_run_week_attribution(metadata: object, week: int) -> bool | None:
    """Return whether explicit metadata covers week; never inspect timestamps."""
    if not isinstance(metadata, dict):
        return None
    if _is_int(metadata.get("week")):
        return metadata["week"] == week
    weeks = metadata.get("weeks")
    if isinstance(weeks, list) and all(_is_int(value) for value in weeks):
        return week in weeks
    start_week = metadata.get("start_week")
    end_week = metadata.get("end_week")
    if _is_int(start_week) and _is_int(end_week):
        return start_week <= week <= end_week
    return None


def scan_ingest_tag_dml(repo_root: Path = ROOT, source: str | None = None) -> int:
    paths = (
        [repo_root / "scripts" / f"ingest_{source}.py"]
        if source
        else sorted((repo_root / "scripts").glob("ingest_*.py"))
    )
    matches = 0
    for path in paths:
        if not path.exists():
            raise UsageError(f"missing ingest script: {path.relative_to(repo_root)}")
        matches += len(INGEST_DML_PATTERN.findall(path.read_text(encoding="utf-8")))
    return matches


def build_hard_fails(
    *,
    n_duplicate_external_id: int,
    n_source_family_promotions: int,
    n_ingest_tag_dml: int,
    ingest_runs: Sequence[Mapping[str, Any]],
    retry_reason: str | None = None,
    retry_count: int = 0,
) -> list[str]:
    failures: list[str] = []
    if n_duplicate_external_id:
        failures.append(f"duplicate_external_id: {n_duplicate_external_id}")
    if n_source_family_promotions:
        failures.append(
            f"source_play_class_promoted_to_play_family: {n_source_family_promotions}"
        )
    if n_ingest_tag_dml:
        failures.append(f"trusted_tag_write_in_ingest_code: {n_ingest_tag_dml}")
    if not ingest_runs:
        failures.append("ingest_run_not_found")
    if any(row.get("status") == "failed" for row in ingest_runs) and not retry_reason:
        failures.append("ingest_run_failed")
    if retry_reason and retry_count >= 2:
        failures.append("retry_limit_reached")
    return failures


async def query_live(database_url: str, season: int, week: int, source: str) -> dict[str, Any]:
    try:
        import asyncpg
    except ImportError as exc:  # pragma: no cover - dependency is present in project installs
        raise UsageError("asyncpg is required for live database mode") from exc

    conn = await asyncpg.connect(database_url, command_timeout=30)
    try:
        counts_row = await conn.fetchrow(PLAY_COUNTS_SQL, season, week, source)
        duplicate_count = await conn.fetchval(DUPLICATE_IDS_SQL, season, week, source)
        promotion_count = await conn.fetchval(
            SOURCE_FAMILY_PROMOTIONS_SQL, season, week, source
        )
        ingest_rows = await conn.fetch(INGEST_RUNS_SQL, season, source)
    finally:
        await conn.close()

    return {
        "n_plays": int(counts_row["n_plays"]),
        "n_unknown_family": int(counts_row["n_unknown_family"]),
        "n_unknown_formation": int(counts_row["n_unknown_formation"]),
        "n_missing_external_id": int(counts_row["n_missing_external_id"]),
        "n_duplicate_external_id": int(duplicate_count),
        "n_source_family_promotions": int(promotion_count),
        "ingest_runs": [dict(row) for row in ingest_rows],
        "retry_reason": None,
    }


def _summary_value(value: object) -> str:
    if value is None:
        return "NOT IN THE EVIDENCE"
    return str(value)


def render_report(
    *,
    season: int,
    week: int,
    source: str,
    retry_count: int,
    counts: Mapping[str, Any],
    hard_fails: Sequence[str],
    assumption_no_live_db: bool,
) -> str:
    lines = [
        "# Sunday Source-Triage Staged Report",
        "",
        f"- Season: {season}",
        f"- Week: {week}",
        f"- Source: {source}",
        f"- Retry count: {retry_count}",
    ]
    if assumption_no_live_db:
        lines.extend(("- ASSUMPTION: no live DB", ""))
    else:
        lines.append("")

    lines.extend(
        (
            "## Counts",
            "",
            f"- n_plays: {counts['n_plays']}",
            f"- n_unknown_family: {counts['n_unknown_family']}",
            f"- n_unknown_formation: {counts['n_unknown_formation']}",
            f"- n_missing_external_id: {counts['n_missing_external_id']}",
            "",
            "## Ingest runs",
            "",
        )
    )
    ingest_runs = counts["ingest_runs"]
    if not ingest_runs:
        lines.append("- NOT IN THE EVIDENCE: settled ingest run")
    for row in ingest_runs:
        lines.extend(
            (
                f"- id: {_summary_value(row.get('id'))}",
                f"  - status: {_summary_value(row.get('status'))}",
                f"  - rows_seen: {_summary_value(row.get('rows_seen'))}",
                f"  - rows_inserted: {_summary_value(row.get('rows_inserted'))}",
                f"  - rows_updated: {_summary_value(row.get('rows_updated'))}",
                f"  - rows_skipped: {_summary_value(row.get('rows_skipped'))}",
                f"  - error_count: {_summary_value(row.get('error_count'))}",
            )
        )
        attribution = ingest_run_week_attribution(row.get("metadata"), week)
        if attribution is None:
            lines.append("  - NOT IN THE EVIDENCE: ingest run week attribution")
        else:
            lines.append(f"  - target_week_attributed: {str(attribution).lower()}")

    lines.extend(("", "## Hard fails", ""))
    if hard_fails:
        lines.extend(f"- {failure}" for failure in hard_fails)
    else:
        lines.append("- none")
    lines.extend(("", "Human gate required. This report is staged, not approved.", ""))
    return "\n".join(lines)


def validate_return_object(payload: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    required = set(schema["required"])
    allowed = set(schema["properties"])
    keys = set(payload)
    if keys != required or not keys <= allowed:
        missing = sorted(required - keys)
        extra = sorted(keys - allowed)
        raise ValueError(f"invalid return keys; missing={missing}, extra={extra}")
    for key in ("season", "week", "n_plays", "n_unknown_family", "n_unknown_formation", "n_missing_external_id"):
        if not _is_int(payload[key]) or payload[key] < 0:
            raise ValueError(f"{key} must be a non-negative integer")
    if payload["source"] not in ("cfbd", "nflverse"):
        raise ValueError("invalid source")
    if not isinstance(payload["hard_fails"], list) or any(
        not isinstance(value, str) or not value for value in payload["hard_fails"]
    ):
        raise ValueError("hard_fails must be an array of non-empty strings")
    if payload["report_path"] != "agent/sunday-triage/report.md":
        raise ValueError("invalid report_path")
    verdict = payload["verdict"]
    retry_reason = payload["retry_reason"]
    if verdict == "pass" and (payload["hard_fails"] or retry_reason is not None):
        raise ValueError("pass requires no hard fails or retry reason")
    if verdict == "fail" and (not payload["hard_fails"] or retry_reason is not None):
        raise ValueError("fail requires hard fails and no retry reason")
    if verdict == "retry" and (
        payload["hard_fails"] or not isinstance(retry_reason, str) or not retry_reason
    ):
        raise ValueError("retry requires no hard fails and a retry reason")
    if verdict not in ("pass", "fail", "retry"):
        raise ValueError("invalid verdict")


async def stage(args: argparse.Namespace, repo_root: Path = ROOT) -> tuple[dict[str, Any], int]:
    if args.season < 0 or args.week < 0:
        raise UsageError("--season and --week must be non-negative")
    if args.retry_count < 0 or args.retry_count > 2:
        raise UsageError("--retry-count must be from 0 through 2")
    database_url = args.database_url or os.getenv("DATABASE_URL")
    assumption_no_live_db = not bool(database_url)
    if database_url:
        if args.counts_json:
            raise UsageError("--counts-json cannot be used with a database URL")
        counts = await query_live(database_url, args.season, args.week, args.source)
    else:
        if not args.counts_json:
            raise UsageError("--counts-json is required when no DATABASE_URL is available")
        counts = load_exported_counts(args.counts_json, args.season, args.source)

    retry_reason = counts.get("retry_reason")
    n_ingest_tag_dml = scan_ingest_tag_dml(repo_root)
    hard_fails = build_hard_fails(
        n_duplicate_external_id=counts["n_duplicate_external_id"],
        n_source_family_promotions=counts["n_source_family_promotions"],
        n_ingest_tag_dml=n_ingest_tag_dml,
        ingest_runs=counts["ingest_runs"],
        retry_reason=retry_reason,
        retry_count=args.retry_count,
    )
    if hard_fails:
        verdict = "fail"
        retry_reason = None
    elif retry_reason:
        verdict = "retry"
    else:
        verdict = "pass"

    report_path = repo_root / "agent" / "sunday-triage" / "report.md"
    report_path.write_text(
        render_report(
            season=args.season,
            week=args.week,
            source=args.source,
            retry_count=args.retry_count,
            counts=counts,
            hard_fails=hard_fails,
            assumption_no_live_db=assumption_no_live_db,
        ),
        encoding="utf-8",
    )
    result = {
        "season": args.season,
        "week": args.week,
        "source": args.source,
        "n_plays": counts["n_plays"],
        "n_unknown_family": counts["n_unknown_family"],
        "n_unknown_formation": counts["n_unknown_formation"],
        "n_missing_external_id": counts["n_missing_external_id"],
        "hard_fails": hard_fails,
        "report_path": "agent/sunday-triage/report.md",
        "verdict": verdict,
        "retry_reason": retry_reason,
    }
    schema = json.loads((repo_root / "agent" / "sunday-triage" / "40-returns.schema.json").read_text())
    validate_return_object(result, schema)
    return result, 2 if hard_fails else 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        result, exit_code = asyncio.run(stage(args))
    except UsageError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
