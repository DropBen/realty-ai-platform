"""Bounded HTTP load baseline on a newly created fictional deployment."""

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, insert, inspect
from sqlalchemy.engine import make_url


def percentile(values, percent):
    values = sorted(values)
    return round(values[min(len(values) - 1, int((len(values) - 1) * percent))], 2)


def stop(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False
        )
    else:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


async def workload(base_url, database_url):
    from realty.models import Contact, Property

    clients, anchors = [], []
    samples, errors = [], []
    engine = create_engine(database_url)
    for index in range(3):
        client = httpx.AsyncClient(base_url=base_url, timeout=30)
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": f"Load Agent {index}",
                "email": f"load-{index}@example.com",
                "password": "Fictional-load-password-2026",
                "organization": f"Load agency {index}",
            },
        )
        response.raise_for_status()
        body = response.json()
        client.headers["X-CSRF-Token"] = body["csrf_token"]
        org = body["organization"]["id"]
        anchor = str(uuid4())
        with engine.begin() as connection:
            connection.execute(
                insert(Contact),
                [
                    {
                        "id": anchor if n == 0 else str(uuid4()),
                        "org_id": org,
                        "name": f"Fixture client {n}",
                        "email": f"fixture-{index}-{n}@example.com",
                        "kind": "buyer",
                        "score": n % 100,
                    }
                    for n in range(1000)
                ],
            )
            connection.execute(
                insert(Property),
                [
                    {
                        "org_id": org,
                        "address": f"{n + 1} Fixture Lane",
                        "location": "Example City",
                        "price": 500000 + n * 1000,
                        "bedrooms": 3,
                        "bathrooms": 2,
                    }
                    for n in range(100)
                ],
            )
        clients.append(client)
        anchors.append(anchor)

    async def send(client, method, path, label, body=None):
        started = time.perf_counter()
        try:
            response = await client.request(method, "/api/v1" + path, json=body)
            samples.append((label, (time.perf_counter() - started) * 1000, response.status_code))
            if not 200 <= response.status_code < 300:
                errors.append({"route": label, "status": response.status_code})
                return None
            return response.json()
        except httpx.HTTPError:
            samples.append((label, (time.perf_counter() - started) * 1000, 0))
            errors.append({"route": label, "status": 0})
            return None

    async def actor(index):
        client, anchor = clients[index], anchors[index]
        for n in range(60):
            kind = n % 10
            if kind == 0:
                await send(client, "GET", "/crm/contacts?q=Fixture&page_size=25", "contact_search")
            elif kind == 1:
                await send(client, "GET", "/briefing", "briefing")
            elif kind == 2:
                await send(client, "GET", "/analytics", "analytics")
            elif kind == 3:
                await send(client, "GET", "/crm/properties", "properties")
            elif kind == 4:
                await send(client, "GET", f"/contacts/{anchor}/profile", "living_profile")
            elif kind == 5:
                await send(
                    client,
                    "POST",
                    "/command",
                    "structured_command",
                    {"question": "Who are my hottest leads?"},
                )
            elif kind == 6:
                await send(
                    client,
                    "POST",
                    "/crm/tasks",
                    "create_task",
                    {"title": f"Fixture follow-up {n}", "contact_id": anchor},
                )
            elif kind == 7:
                await send(
                    client,
                    "PUT",
                    f"/contacts/{anchor}/preferences",
                    "update_preferences",
                    {"budget_max": 700000 + n, "bedrooms": 3},
                )
            elif kind == 8:
                await send(
                    client,
                    "POST",
                    f"/contacts/{anchor}/notes",
                    "create_note",
                    {"title": f"Fixture note {n}", "body": "Fictional load-test record"},
                )
            else:
                action = await send(
                    client,
                    "POST",
                    "/actions",
                    "propose_task",
                    {
                        "kind": "create_task",
                        "title": "Fictional follow-up",
                        "reason": "Explicit load-test fixture",
                        "contact_id": anchor,
                        "payload": {"title": f"Approved fixture {n}", "contact_id": anchor},
                    },
                )
                if action:
                    await send(
                        client,
                        "POST",
                        f"/actions/{action['id']}/decision",
                        "approve_task",
                        {"decision": "approve", "version": action["version"]},
                    )

    started = time.perf_counter()
    await asyncio.gather(*(actor(i) for i in range(3)))
    elapsed = time.perf_counter() - started
    # Confirm queued work completes; request counts remain below normal per-user limits.
    deadline = time.monotonic() + 30
    completed = False
    while time.monotonic() < deadline:
        states = [(await client.get("/api/v1/operations")).json() for client in clients]
        completed = all(state.get("jobs", {}).get("done", 0) >= 6 for state in states)
        if completed:
            break
        await asyncio.sleep(1)
    isolated = (await clients[1].get(f"/api/v1/crm/contacts/{anchors[0]}")).status_code == 404
    for client in clients:
        await client.aclose()
    engine.dispose()
    groups = defaultdict(list)
    for label, duration, _status in samples:
        groups[label].append(duration)
    durations = [duration for _, duration, _ in samples]
    return {
        "scope": "Short isolated functional load baseline with fictional data; not a capacity or production SLO certification.",
        "database": make_url(database_url).get_backend_name(),
        "virtual_users": 3,
        "contacts": 3000,
        "properties": 300,
        "requests": len(samples),
        "elapsed_seconds": round(elapsed, 3),
        "requests_per_second": round(len(samples) / elapsed, 2),
        "latency_ms": {
            "p50": percentile(durations, 0.5),
            "p95": percentile(durations, 0.95),
            "max": round(max(durations), 2),
        },
        "errors": errors,
        "worker_completed_approved_tasks": completed,
        "cross_tenant_request_rejected": isolated,
        "routes": {
            key: {
                "requests": len(values),
                "p50_ms": percentile(values, 0.5),
                "p95_ms": percentile(values, 0.95),
            }
            for key, values in groups.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--postgres", action="store_true")
    args = parser.parse_args()
    root = args.work_dir.resolve() / ("load-" + uuid4().hex)
    root.mkdir(parents=True)
    database = (
        os.environ.get("LOAD_DATABASE_URL", "")
        if args.postgres
        else "sqlite:///" + (root / "load.sqlite3").as_posix()
    )
    if args.postgres and not (make_url(database).database or "").startswith("realty_load_"):
        parser.error("Use a dedicated realty_load_* database")
    engine = create_engine(database)
    if inspect(engine).get_table_names():
        raise ValueError("Load baseline requires a new empty database")
    engine.dispose()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path("backend").resolve()),
        "DATABASE_URL": database,
        "APP_ENV": "test",
        "DEMO_MODE": "true",
        "AI_PROVIDER": "disabled",
        "MAIL_BACKEND": "disabled",
        "REQUIRE_EMAIL_VERIFICATION": "false",
        "ENCRYPTION_KEY": "",
        "COOKIE_SECURE": "false",
        "APP_ORIGIN": base,
        "STORAGE_PATH": str(root / "documents"),
    }
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
        creationflags=creationflags,
    )
    processes = []
    with (
        (root / "api.log").open("w", encoding="utf-8") as api_log,
        (root / "worker.log").open("w", encoding="utf-8") as worker_log,
    ):
        try:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "realty.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--no-access-log",
                    ],
                    env=environment,
                    stdout=api_log,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
            )
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-m", "realty.jobs"],
                    env=environment,
                    stdout=worker_log,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
            )
            with httpx.Client(timeout=2) as client:
                for _attempt in range(60):
                    try:
                        if client.get(base + "/health/ready").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Isolated API did not become ready")
            report = asyncio.run(workload(base, database))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(
                json.dumps(
                    {key: value for key, value in report.items() if key != "routes"}, indent=2
                )
            )
            if (
                report["errors"]
                or not report["worker_completed_approved_tasks"]
                or not report["cross_tenant_request_rejected"]
            ):
                raise RuntimeError("Load verification failed")
        finally:
            for process in reversed(processes):
                stop(process)


if __name__ == "__main__":
    main()
