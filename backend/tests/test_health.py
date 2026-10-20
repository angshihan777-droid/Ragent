"""健康检查：worker 心跳与队列积压，不连真实 PG/Redis。"""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.routers import health


class _Redis:
    def __init__(self, keys):
        self.keys = keys

    async def scan_iter(self, **_kwargs):
        for key in self.keys:
            yield key


class _Acquire:
    def __init__(self, row):
        self.row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def fetchrow(self, *_args):
        return self.row


class _Pool:
    def __init__(self, row):
        self.row = row

    def acquire(self):
        return _Acquire(self.row)


def test_check_worker_true_when_heartbeat_exists(monkeypatch):
    monkeypatch.setattr(db, "redis_client", _Redis(["ragent:worker:w1"]))
    assert asyncio.run(db.check_worker()) is True


def test_check_worker_false_without_heartbeat(monkeypatch):
    monkeypatch.setattr(db, "redis_client", _Redis([]))
    assert asyncio.run(db.check_worker()) is False


def test_queue_snapshot_reports_backlog(monkeypatch):
    row = {"pending": 3, "running": 1, "oldest_pending_seconds": 12.34}
    monkeypatch.setattr(db, "pg_pool", _Pool(row))

    assert asyncio.run(db.queue_snapshot()) == {
        "pending": 3,
        "running": 1,
        "oldest_pending_seconds": 12.3,
    }


def test_ready_returns_200_when_all_dependencies_alive(monkeypatch):
    async def yes():
        return True

    async def queue():
        return {"pending": 0, "running": 0, "oldest_pending_seconds": None}

    monkeypatch.setattr(health, "check_postgres", yes)
    monkeypatch.setattr(health, "check_redis", yes)
    monkeypatch.setattr(health, "check_worker", yes)
    monkeypatch.setattr(health, "queue_snapshot", queue)

    app = FastAPI()
    app.include_router(health.router)
    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json()["worker"] is True


def test_ready_returns_503_when_worker_is_missing(monkeypatch):
    async def yes():
        return True

    async def no():
        return False

    async def queue():
        return {"pending": 2, "running": 0, "oldest_pending_seconds": 8.0}

    monkeypatch.setattr(health, "check_postgres", yes)
    monkeypatch.setattr(health, "check_redis", yes)
    monkeypatch.setattr(health, "check_worker", no)
    monkeypatch.setattr(health, "queue_snapshot", queue)

    app = FastAPI()
    app.include_router(health.router)
    response = TestClient(app).get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["worker"] is False
    assert body["queue"]["pending"] == 2
