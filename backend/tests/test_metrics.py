"""用量统计：纯函数与聚合映射，不连数据库。"""
import asyncio

import pytest

from app.services import metrics
from app.services.metrics import estimate_cost, success_rate


def test_success_rate_returns_none_without_finished_runs():
    assert success_rate(0, 0) is None


def test_success_rate_counts_failed_runs():
    assert success_rate(9, 1) == 0.9
    assert success_rate(0, 3) == 0.0


def test_estimate_cost_returns_none_when_prices_are_unset():
    assert estimate_cost(1000, 1000, 0.0, 0.0) is None


def test_estimate_cost_uses_per_1k_prices():
    # 1000 输入 × 0.001 + 2000 输出 × 0.002 = 0.005
    assert estimate_cost(1000, 2000, 0.001, 0.002) == 0.005


def test_estimate_cost_allows_only_one_price_configured():
    assert estimate_cost(1000, 2000, 0.0, 0.002) == 0.004


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


def test_get_summary_maps_row_and_computes_cost(monkeypatch):
    row = {
        "input_tokens": 1200, "output_tokens": 800, "llm_calls": 3,
        "done_runs": 9, "failed_runs": 1,
    }
    async def fake_prices(_pool, _owner):
        return 0.001, 0.002

    monkeypatch.setattr(metrics.llm_config, "get_cost_prices", fake_prices)

    result = asyncio.run(metrics.get_summary(_Pool(row), "u-1", 7))

    assert result["input_tokens"] == 1200
    assert result["output_tokens"] == 800
    assert result["success_rate"] == 0.9
    assert result["estimated_cost"] == 0.0028


def test_get_summary_handles_null_usage(monkeypatch):
    row = {
        "input_tokens": 0, "output_tokens": 0, "llm_calls": 0,
        "done_runs": 0, "failed_runs": 0,
    }
    async def fake_prices(_pool, _owner):
        return 0.0, 0.0

    monkeypatch.setattr(metrics.llm_config, "get_cost_prices", fake_prices)

    result = asyncio.run(metrics.get_summary(_Pool(row), "u-1", 7))

    assert result["success_rate"] is None
    assert result["estimated_cost"] is None


def test_get_summary_uses_effective_config_prices(monkeypatch):
    row = {
        "input_tokens": 1000, "output_tokens": 1000, "llm_calls": 2,
        "done_runs": 1, "failed_runs": 0,
    }
    async def fake_prices(_pool, _owner):
        return 0.01, 0.02

    monkeypatch.setattr(metrics.llm_config, "get_cost_prices", fake_prices)

    result = asyncio.run(metrics.get_summary(_Pool(row), "u-1", 7))

    assert result["estimated_cost"] == 0.03
