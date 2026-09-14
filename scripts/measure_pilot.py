"""Measure 20 authenticated Play Finder reads without mutating pilot data."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REQUEST_COUNT = 20


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 20 read-only authenticated GETs against pilot Play Finder."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token", help="Bearer token; defaults to FIELDMIND_TOKEN")
    parser.add_argument("--program-id", help="Optional X-Program-ID for a multi-program user")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    args.token = args.token or os.getenv("FIELDMIND_TOKEN")
    if not args.token:
        parser.error("--token or FIELDMIND_TOKEN is required")
    return args


def main() -> int:
    args = parse_args()
    query = urlencode({"limit": 1})
    url = f"{args.base_url.rstrip('/')}/api/v1/plays?{query}"
    headers = {"Authorization": f"Bearer {args.token}"}
    if args.program_id:
        headers["X-Program-ID"] = args.program_id

    elapsed_ms: list[float] = []
    try:
        for _ in range(REQUEST_COUNT):
            request = Request(url, headers=headers, method="GET")
            started = time.perf_counter()
            with urlopen(request, timeout=args.timeout) as response:
                response.read()
                if response.status != 200:
                    raise RuntimeError(f"unexpected HTTP status {response.status}")
            elapsed_ms.append((time.perf_counter() - started) * 1000)
    except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "detail": str(exc)}))
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "method": "GET",
                "path": "/api/v1/plays?limit=1",
                "requests": REQUEST_COUNT,
                "p50_ms": round(percentile(elapsed_ms, 0.50), 2),
                "p95_ms": round(percentile(elapsed_ms, 0.95), 2),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
