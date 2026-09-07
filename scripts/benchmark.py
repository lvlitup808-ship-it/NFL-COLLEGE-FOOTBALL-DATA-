import argparse
import asyncio
import json
import math
import os
import time
from typing import Any, Awaitable, Callable

import asyncpg


QueryFn = Callable[[], Awaitable[Any]]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(p * len(ordered)) - 1)
    return ordered[index]


async def time_query(fn: QueryFn, warmup: int, iterations: int) -> list[float]:
    for _ in range(warmup):
        await fn()
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        await fn()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


async def main(iterations: int, warmup: int) -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    conn = await asyncpg.connect(database_url, command_timeout=8)
    try:
        await conn.execute("SET statement_timeout='6000ms'")
        has_schema = await conn.fetchval("SELECT to_regclass('public.benchmark_runs') IS NOT NULL")
        if not has_schema:
            raise RuntimeError("database is not migrated; run `python scripts/migrate.py` first")

        combo = await conn.fetchrow(
            """
            SELECT offense_team_name,down,distance_bucket,field_zone,COUNT(*) AS n
            FROM plays
            GROUP BY offense_team_name,down,distance_bucket,field_zone
            ORDER BY n DESC
            LIMIT 1
            """
        )
        if not combo:
            raise RuntimeError("no plays available to benchmark")
        opponent = combo["offense_team_name"]

        async def play_filter() -> Any:
            return await conn.fetch(
                """
                SELECT id,game_id,play_sequence,quarter,clock,down,distance,yard_line,
                       play_family,concept,epa,success,explosive
                FROM plays
                WHERE offense_team_name=$1 AND down=$2
                  AND distance_bucket=$3 AND field_zone=$4
                ORDER BY game_id,play_sequence
                LIMIT 20
                """,
                combo["offense_team_name"],
                combo["down"],
                combo["distance_bucket"],
                combo["field_zone"],
            )

        async def opponent_report() -> Any:
            return await conn.fetch(
                """
                SELECT play_family,COUNT(*)::int AS n,
                       AVG(epa) AS avg_epa,
                       AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS success_rate
                FROM plays
                WHERE offense_team_name=$1
                GROUP BY play_family
                ORDER BY n DESC
                """,
                opponent,
            )

        async def self_scout() -> Any:
            return await conn.fetch(
                """
                SELECT play_family,COUNT(*)::int AS n,
                       SUM(CASE WHEN explosive THEN 1 ELSE 0 END)::int AS explosives,
                       SUM(CASE WHEN NOT success THEN 1 ELSE 0 END)::int AS failures,
                       AVG(epa) AS avg_epa
                FROM plays
                WHERE offense_team_name=$1
                GROUP BY play_family
                ORDER BY avg_epa DESC NULLS LAST
                """,
                opponent,
            )

        cases: list[tuple[str, QueryFn, float, dict[str, Any]]] = [
            (
                "play_filter_20",
                play_filter,
                2000.0,
                {
                    "team": combo["offense_team_name"],
                    "down": combo["down"],
                    "distance_bucket": combo["distance_bucket"],
                    "field_zone": combo["field_zone"],
                },
            ),
            ("opponent_report", opponent_report, 5000.0, {"opponent": opponent}),
            ("self_scout", self_scout, 5000.0, {"team": opponent}),
        ]

        results: list[dict[str, Any]] = []
        all_passed = True
        for name, fn, threshold_ms, parameters in cases:
            samples = await time_query(fn, warmup, iterations)
            p50 = percentile(samples, 0.50)
            p95 = percentile(samples, 0.95)
            maximum = max(samples)
            passed = p95 < threshold_ms
            all_passed = all_passed and passed
            result = {
                "query": name,
                "iterations": iterations,
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "max_ms": round(maximum, 2),
                "threshold_ms": threshold_ms,
                "passed": passed,
                "parameters": parameters,
            }
            results.append(result)
            await conn.execute(
                """
                INSERT INTO benchmark_runs (
                    query_name,parameters,sample_count,p50_ms,p95_ms,max_ms,
                    pass_threshold_ms,passed
                ) VALUES ($1,$2::jsonb,$3,$4,$5,$6,$7,$8)
                """,
                name,
                json.dumps(parameters),
                iterations,
                p50,
                p95,
                maximum,
                threshold_ms,
                passed,
            )

        play_count = await conn.fetchval("SELECT COUNT(*) FROM plays")
        print(
            json.dumps(
                {"status": "pass" if all_passed else "fail", "play_count": play_count, "results": results},
                separators=(",", ":"),
            )
        )
        return 0 if all_passed else 1
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark FIELDMIND V1 decision queries")
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--warmup", type=int, default=3)
    args = parser.parse_args()
    if args.iterations < 1 or args.iterations > 500:
        parser.error("--iterations must be between 1 and 500")
    if args.warmup < 0 or args.warmup > 50:
        parser.error("--warmup must be between 0 and 50")
    return args


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(main(args.iterations, args.warmup)))
