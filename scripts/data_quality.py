import asyncio
import json
import os
from typing import Any

import asyncpg


async def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    conn = await asyncpg.connect(database_url, command_timeout=8)
    try:
        source_rows = await conn.fetch(
            """
            SELECT p.external_source AS source,g.season,
                   COUNT(*)::int AS plays,
                   SUM(CASE WHEN p.epa IS NOT NULL THEN 1 ELSE 0 END)::int AS epa_n,
                   SUM(CASE WHEN p.ppa IS NOT NULL THEN 1 ELSE 0 END)::int AS ppa_n,
                   SUM(CASE WHEN p.formation='UNKNOWN' THEN 1 ELSE 0 END)::int AS unknown_formation_n,
                   SUM(CASE WHEN p.personnel_offense='UNKNOWN' THEN 1 ELSE 0 END)::int AS unknown_personnel_n
            FROM plays p JOIN games g ON g.id=p.game_id
            WHERE p.external_source IS NOT NULL
            GROUP BY p.external_source,g.season
            ORDER BY p.external_source,g.season
            """
        )
        missing_play_identity = await conn.fetchval(
            """
            SELECT COUNT(*) FROM plays
            WHERE external_source IS NOT NULL AND (external_id IS NULL OR external_id='')
            """
        )
        missing_game_identity = await conn.fetchval(
            """
            SELECT COUNT(*) FROM games
            WHERE external_source IS NOT NULL AND (external_id IS NULL OR external_id='')
            """
        )
        duplicate_play_identity = await conn.fetchval(
            """
            SELECT COUNT(*) FROM (
              SELECT external_source,external_id
              FROM plays
              WHERE external_source IS NOT NULL AND external_id IS NOT NULL
              GROUP BY external_source,external_id HAVING COUNT(*) > 1
            ) d
            """
        )
        orphan_ingest_runs = await conn.fetchval(
            """
            SELECT COUNT(*) FROM ingest_runs
            WHERE status='running' AND started_at < now() - interval '6 hours'
            """
        )
        cfbd_metric_mismatch = await conn.fetchval(
            """
            SELECT COUNT(*) FROM plays
            WHERE external_source='cfbd' AND ppa IS NULL AND epa IS NOT NULL
            """
        )

        hard_failures = {
            "missing_play_external_identity": int(missing_play_identity or 0),
            "missing_game_external_identity": int(missing_game_identity or 0),
            "duplicate_play_external_identity": int(duplicate_play_identity or 0),
        }
        warnings = {
            "stale_running_ingest_runs": int(orphan_ingest_runs or 0),
            "cfbd_rows_with_epa_but_no_ppa": int(cfbd_metric_mismatch or 0),
        }
        sources: list[dict[str, Any]] = []
        for row in source_rows:
            data = dict(row)
            plays = data["plays"] or 1
            data["epa_coverage_pct"] = round(100 * data["epa_n"] / plays, 1)
            data["ppa_coverage_pct"] = round(100 * data["ppa_n"] / plays, 1)
            data["unknown_formation_pct"] = round(100 * data["unknown_formation_n"] / plays, 1)
            data["unknown_personnel_pct"] = round(100 * data["unknown_personnel_n"] / plays, 1)
            sources.append(data)

        passed = all(value == 0 for value in hard_failures.values())
        print(
            json.dumps(
                {
                    "status": "pass" if passed else "fail",
                    "hard_failures": hard_failures,
                    "warnings": warnings,
                    "sources": sources,
                },
                separators=(",", ":"),
                default=str,
            )
        )
        return 0 if passed else 1
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
