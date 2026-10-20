"""审计写入：只测参数映射，不连数据库。"""
import asyncio
import json

from app.services import audit


class _Conn:
    def __init__(self):
        self.args = None

    async def execute(self, sql, *args):
        self.args = (sql, args)


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self):
        self.conn = _Conn()

    def acquire(self):
        return _Acquire(self.conn)


def test_audit_record_maps_action_and_json_detail():
    pool = _Pool()
    asyncio.run(audit.record(pool, "u-1", "rate_limited", retry_after=42))

    _, (owner, action, detail) = pool.conn.args
    assert owner == "u-1"
    assert action == "rate_limited"
    assert json.loads(detail) == {"retry_after": 42}


def test_audit_record_ignores_missing_pool():
    asyncio.run(audit.record(None, "u-1", "blocked"))
