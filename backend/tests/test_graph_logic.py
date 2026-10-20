"""图里的纯逻辑节点：引用校验、补查路由、上下文截断。"""
import asyncio

from langchain_core.messages import AIMessage, HumanMessage

from app.agent import graph


def test_elapsed_ms_never_negative():
    assert graph._elapsed_ms(10.0, 10.123) == 123
    assert graph._elapsed_ms(10.0, 9.0) == 0


class _Acquire:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def acquire(self):
        return _Acquire()


def test_context_uses_app_thread_id_not_checkpoint_key(monkeypatch):
    seen = {}

    async def fake_history(_conn, thread_id, _request_id):
        seen["thread_id"] = thread_id
        return []

    async def fake_count(_conn, _project_id):
        return 0

    monkeypatch.setattr(graph, "history_before_request", fake_history)
    monkeypatch.setattr(graph.documents, "count_documents", fake_count)
    config = {"configurable": {
        "pool": _Pool(), "thread_id": "thread:request",
        "app_thread_id": "thread", "request_id": "request", "project_id": "project",
    }}

    asyncio.run(graph._context({"question": "q"}, config))

    assert seen["thread_id"] == "thread"


def _state(**kw):
    base = {"sources": [], "queries": [], "rounds": 1, "sufficient": False, "action": "retrieve"}
    return {**base, **kw}


# ---- _validate：引用编号合法性校验 ----

def test_validate_removes_unknown_citation():
    state = _state(sources=[{"citation_id": "S1"}], response="结论A [S1]，结论B [S9]")
    assert asyncio.run(graph._validate(state))["response"] == "结论A [S1]，结论B "


def test_validate_rejects_retrieval_answer_without_citation():
    state = _state(sources=[{"citation_id": "S1"}], response="没有引用的回答")
    assert "没有提供有效引用" in asyncio.run(graph._validate(state))["response"]


def test_validate_keeps_direct_answer_without_sources():
    state = _state(action="direct", response="你好")
    assert asyncio.run(graph._validate(state))["response"] == "你好"


# ---- _after_check：补查路由 ----

def test_after_check_rewrites_when_insufficient_with_new_query():
    state = _state(queries=["年假几天"], next_query="年假 入职满一年")
    assert graph._after_check(state) == "rewrite"


def test_after_check_stops_on_duplicate_query_ignoring_space_and_case():
    state = _state(queries=["Annual Leave"], next_query=" annual  leave ")
    assert graph._after_check(state) == "answer"


def test_after_check_stops_at_max_rounds():
    state = _state(rounds=graph.MAX_RETRIEVAL_ROUNDS, next_query="新问题")
    assert graph._after_check(state) == "answer"


def test_after_check_answers_when_sufficient():
    assert graph._after_check(_state(sufficient=True, next_query="x")) == "answer"


def test_after_check_does_not_retry_on_retrieval_error():
    assert graph._after_check(_state(retrieval_error="挂了", next_query="x")) == "answer"


# ---- _context：打标签 + 截断 + 拼接 ----

class _Conn:
    """只实现 _context 用到的那个查询：本项目的资料篇数。"""

    async def fetchval(self, query, *args):
        return 3


class _Acquire:
    async def __aenter__(self):
        return _Conn()

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def acquire(self):
        return _Acquire()


def _run_context_state(monkeypatch, history):
    async def fake_history(conn, thread_id, request_id):
        return history
    monkeypatch.setattr(graph, "history_before_request", fake_history)
    config = {"configurable": {"pool": _Pool(), "thread_id": "t", "request_id": "r",
                               "project_id": "p"}}
    return asyncio.run(graph._context({"question": "Q"}, config))


def _run_context(monkeypatch, history):
    return _run_context_state(monkeypatch, history)["messages"]


def _row(role, n):
    return {"role": role, "content": "x" * n}


def test_context_keeps_newest_within_budget(monkeypatch):
    msgs = _run_context(monkeypatch, [_row("user", 1000), _row("assistant", 9000),
                                      _row("user", 1000), _row("assistant", 3000)])
    assert [(type(m), len(m.content)) for m in msgs] == [
        (HumanMessage, 1000), (AIMessage, 3000), (HumanMessage, 1)]


def test_context_drops_leading_orphan_ai_reply(monkeypatch):
    msgs = _run_context(monkeypatch, [_row("user", 5000), _row("assistant", 7000),
                                      _row("user", 100), _row("assistant", 100)])
    assert isinstance(msgs[0], HumanMessage)


def test_context_without_history_has_only_question(monkeypatch):
    msgs = _run_context(monkeypatch, [])
    assert len(msgs) == 1 and msgs[0].content == "Q"


def test_context_carries_material_count_for_decide(monkeypatch):
    """决策节点靠这个数把「该不该查资料」变成客观判据，而不是让模型猜。"""
    assert _run_context_state(monkeypatch, [])["material_count"] == 3
