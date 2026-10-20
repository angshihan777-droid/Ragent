"""模型配置里的成本单价：读取回显与「None 保留原值」语义。"""
import asyncio
from decimal import Decimal
from types import SimpleNamespace

from app.repositories import llm_config as repo
from app.services import llm_config as svc
from app.services.llm_config import suggest_cost_prices


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, conn=None):
        self.conn = conn or object()

    def acquire(self):
        return _Acquire(self.conn)


def test_config_view_exposes_saved_prices(monkeypatch):
    row = {
        "base_url": "https://api.example/v1",
        "api_key": "sk-x",
        "model": "m",
        "reasoning_effort": "low",
        "cost_input_per_1k": Decimal("0.001"),
        "cost_output_per_1k": Decimal("0.002"),
    }

    async def fake_get_config(_conn, _owner):
        return row

    monkeypatch.setattr(repo, "get_config", fake_get_config)

    view = asyncio.run(svc.get_config_view(_Pool(), "u-1"))

    assert view["cost_input_per_1k"] == 0.001
    assert view["cost_output_per_1k"] == 0.002
    assert view["key_set"] is True


def test_suggest_prices_for_deepseek_flash():
    assert suggest_cost_prices("https://api.deepseek.com/v1", "deepseek-flash") == (0.002, 0.008)


def test_suggest_prices_accepts_version_suffix():
    assert suggest_cost_prices("https://api.deepseek.com", "deepseek-v4-pro-0813") == (0.009, 0.027)


def test_suggest_prices_ignores_other_providers():
    assert suggest_cost_prices("https://api.openai.com/v1", "deepseek-flash") == (None, None)


def test_suggest_prices_returns_none_for_unknown_model():
    assert suggest_cost_prices("https://api.deepseek.com", "unknown-model") == (None, None)


def test_get_cost_prices_falls_back_without_writing(monkeypatch):
    async def no_row(_conn, _owner):
        return None

    async def must_not_write(*_args, **_kwargs):
        raise AssertionError("只读统计不应创建配置行")

    monkeypatch.setattr(repo, "get_config", no_row)
    monkeypatch.setattr(repo, "upsert_config", must_not_write)
    monkeypatch.setattr(svc, "get_settings", lambda: SimpleNamespace(
        cost_input_per_1k=0.0, cost_output_per_1k=0.0,
    ))

    prices = asyncio.run(svc.get_cost_prices(_Pool(), "u-1"))

    assert prices == (0.0, 0.0)


def test_save_config_keeps_prices_when_not_provided(monkeypatch):
    captured = {}

    async def fake_effective(_pool, _owner):
        return {
            "base_url": "b", "api_key": "k", "model": "m",
            "reasoning_effort": "low",
            "cost_input_per_1k": 0.001, "cost_output_per_1k": 0.002,
        }

    async def fake_upsert(_conn, owner, base_url, api_key, model, effort, ci, co):
        captured.update({
            "owner": owner, "api_key": api_key, "effort": effort,
            "cost_input": ci, "cost_output": co,
        })

    monkeypatch.setattr(svc, "get_effective_config", fake_effective)
    monkeypatch.setattr(repo, "upsert_config", fake_upsert)

    asyncio.run(svc.save_config(_Pool(), "u-1", "b", "m", None, None, None, None))

    assert captured["api_key"] == "k"
    assert captured["effort"] == "low"
    assert captured["cost_input"] == 0.001
    assert captured["cost_output"] == 0.002


def test_save_config_writes_explicit_zero(monkeypatch):
    captured = {}

    async def fake_effective(_pool, _owner):
        return {
            "base_url": "b", "api_key": "k", "model": "m",
            "reasoning_effort": "low",
            "cost_input_per_1k": 0.001, "cost_output_per_1k": 0.002,
        }

    async def fake_upsert(_conn, owner, base_url, api_key, model, effort, ci, co):
        captured.update({"cost_input": ci, "cost_output": co})

    monkeypatch.setattr(svc, "get_effective_config", fake_effective)
    monkeypatch.setattr(repo, "upsert_config", fake_upsert)

    asyncio.run(svc.save_config(_Pool(), "u-1", "b", "m", "k", "low", 0, 0))

    assert captured["cost_input"] == 0
    assert captured["cost_output"] == 0
