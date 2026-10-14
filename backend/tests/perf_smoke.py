"""M6 performance smoke: latency of key list endpoints and concurrent dashboard.

Runs against the live stack (default http://127.0.0.1:8080). Verifies the P0-5
target that ordinary list/search p95 stays under 2s under modest concurrency.

Usage:
  cd backend && .venv/bin/python tests/perf_smoke.py
Env: PERF_BASE_URL, DMS_ADMIN_USERNAME, DMS_ADMIN_PASSWORD
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import time

import httpx

BASE = os.environ.get("PERF_BASE_URL", "http://127.0.0.1:8080")
ADMIN = os.environ.get("DMS_ADMIN_USERNAME", "admin")
PASSWORD = os.environ.get("DMS_ADMIN_PASSWORD", "")


async def login(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"username": ADMIN, "password": PASSWORD}
    )
    r.raise_for_status()
    return r.json()["access_token"]


async def timed(client: httpx.AsyncClient, headers: dict, method: str, path: str, **kw):
    start = time.perf_counter()
    r = await client.request(method, path, headers=headers, **kw)
    elapsed = (time.perf_counter() - start) * 1000
    return r, elapsed


async def bench_path(client, headers, method, path, n=20, **kw):
    samples = []
    statuses = []
    for _ in range(n):
        r, ms = await timed(client, headers, method, path, **kw)
        samples.append(ms)
        statuses.append(r.status_code)
    samples.sort()
    p95 = samples[max(0, int(len(samples) * 0.95) - 1)]
    return {
        "path": path,
        "n": n,
        "ok": sum(1 for s in statuses if s < 400),
        "avg_ms": round(statistics.mean(samples), 1),
        "p95_ms": round(p95, 1),
        "max_ms": round(samples[-1], 1),
    }


async def main() -> int:
    if not PASSWORD:
        print("Set DMS_ADMIN_PASSWORD", file=sys.stderr)
        return 2

    limits = httpx.Limits(max_connections=32, max_keepalive_connections=16)
    # trust_env=False: avoid corporate HTTP_PROXY intercepting 127.0.0.1 and
    # turning nginx's upstream error into a misleading 502.
    async with httpx.AsyncClient(
        base_url=BASE, timeout=30.0, limits=limits, trust_env=False
    ) as client:
        token = await login(client)
        headers = {"Authorization": f"Bearer {token}"}

        paths = [
            ("GET", "/api/v1/employees", {"params": {"page": 1, "page_size": 20}}),
            (
                "GET",
                "/api/v1/employees",
                {"params": {"page": 1, "page_size": 20, "keyword": "a"}},
            ),
            (
                "GET",
                "/api/v1/reports/accommodations",
                {"params": {"page": 1, "page_size": 50}},
            ),
            (
                "GET",
                "/api/v1/reports/vacant-beds",
                {"params": {"page": 1, "page_size": 50}},
            ),
            ("GET", "/api/v1/dashboard/summary", {}),
            (
                "GET",
                "/api/v1/dormitories/tree",
                {"params": {"include_disabled": False}},
            ),
            (
                "GET",
                "/api/v1/workflow/todos",
                {"params": {"status": "pending", "page_size": 20}},
            ),
        ]

        print(f"Performance smoke against {BASE}")
        print(
            f"{'endpoint':<55} {'n':>3} {'ok':>3} {'avg':>10} {'p95':>10} {'max':>10}"
        )
        failures = []
        for method, path, kw in paths:
            row = await bench_path(client, headers, method, path, n=20, **kw)
            print(
                f"{path:<55} {row['n']:>3} {row['ok']:>3} "
                f"{row['avg_ms']:>8.1f}ms {row['p95_ms']:>8.1f}ms {row['max_ms']:>8.1f}ms"
            )
            if row["p95_ms"] > 2000 or row["ok"] < row["n"]:
                failures.append(row)

        async def one():
            r, ms = await timed(client, headers, "GET", "/api/v1/dashboard/summary")
            return r.status_code, ms

        results = await asyncio.gather(*[one() for _ in range(20)])
        oks = sum(1 for s, _ in results if s == 200)
        lat = sorted(ms for _, ms in results)
        p95 = lat[max(0, int(len(lat) * 0.95) - 1)]
        print(
            f"\nconcurrent dashboard x20: ok={oks}/20 p95={p95:.1f}ms max={lat[-1]:.1f}ms"
        )
        if oks < 20 or p95 > 2000:
            failures.append(
                {"path": "concurrent dashboard", "p95_ms": p95, "ok": oks}
            )

        if failures:
            print("\nFAIL: latency/availability budget exceeded:")
            for f in failures:
                print(" ", f)
            return 1
        print("\nPASS: list/search p95 < 2s under smoke load")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
