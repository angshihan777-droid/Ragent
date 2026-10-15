"""P2 服务间鉴权的纯逻辑单测：令牌生成/哈希/解析、身份取值两条来源、中间件发放口径。

沿用项目既有约定：不连真库，用假 pool 驱动分支；用 asyncio.run 而不是 pytest-asyncio
（项目没装那个插件，test_graph_logic / test_owner_isolation 都是这个写法）。
为什么这几条必须钉住：鉴权写错的典型表现不是报错，而是「看着一切正常，但谁都能读」，
靠手工点页面基本发现不了。
"""
import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import deps
from app.middleware.owner import OwnerCookieMiddleware
from app.security import (
    MAX_TOKEN_LENGTH,
    TOKEN_PREFIX,
    generate_token,
    hash_token,
    parse_bearer,
)


# ---- Authorization 头解析：白名单式收窄 ----

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Bearer rag_abc", "rag_abc"),
        ("bearer rag_abc", "rag_abc"),          # RFC 7235：scheme 大小写不敏感
        ("BEARER   rag_abc  ", "rag_abc"),      # 令牌两侧空白可以吃掉
    ],
)
def test_parse_bearer_accepts_valid_forms(raw, expected):
    assert parse_bearer(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "rag_abc",                              # 只有令牌，没有 scheme
        "Basic rag_abc",                        # 别的 scheme 不是我们的令牌
        "Bearer",                               # 只有 scheme
        "Bearer ",                              # 空令牌
        "Bearer a b",                           # 令牌内层空格：清洗会把它折成另一个值
        "Bearer " + "x" * (MAX_TOKEN_LENGTH + 1),   # 超长头，拒在解析层
    ],
)
def test_parse_bearer_rejects_everything_else(raw):
    assert parse_bearer(raw) is None


# ---- 令牌生成与哈希 ----

def test_generate_token_has_prefix_and_enough_entropy():
    token = generate_token()
    assert token.startswith(TOKEN_PREFIX)
    # 32 字节随机 → urlsafe base64 约 43 字符；短于此说明随机源被换掉了
    assert len(token) > 40
    assert generate_token() != token


def test_hash_token_is_deterministic_hex_and_not_the_plaintext():
    token = generate_token()
    digest = hash_token(token)
    assert digest == hash_token(token)           # 确定性：它要当查表键
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
    assert token not in digest                   # 不存明文


# ---- 身份取值：假 pool 驱动两条来源 ----

class _FakeConn:
    """最小连接替身：够 _resolve_token_owner 用。"""

    def __init__(self, owner_id):
        self.owner_id = owner_id
        self.query = None
        self.executed: list[str] = []

    async def fetchval(self, query, *args):
        self.query = query
        return self.owner_id

    async def execute(self, query, *args):
        self.executed.append(query)
        return "UPDATE 1"


class _FakePool:
    def __init__(self, token_owner=None):
        self.conn = _FakeConn(token_owner)

    def acquire(self):
        conn = self.conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


def _make_request(*, authorization=None, cookie_owner=None) -> Request:
    """造一个够 deps.get_owner_id 用的 Request。

    cookie_owner 非空时同时放进 state，模拟 OwnerCookieMiddleware 已经跑过。
    """
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("latin-1")))
    if cookie_owner is not None:
        headers.append((b"cookie", f"ragent_oid={cookie_owner}".encode("latin-1")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
            "headers": headers,
            "state": {"owner_id": cookie_owner} if cookie_owner else {},
        }
    )


def test_bearer_token_wins_over_cookie_identity():
    pool = _FakePool("svc-opsmind")
    request = _make_request(authorization="Bearer rag_x", cookie_owner="u-browser")
    assert asyncio.run(deps.get_owner_id(request, pool)) == "svc-opsmind"
    # 必须真的查了 api_tokens，而不是复用 Cookie 身份
    assert "api_tokens" in pool.conn.query


def test_bearer_token_overwrites_state_for_downstream_readers():
    """下游若直接读 request.state.owner_id，必须看到令牌身份而不是 Cookie 身份。"""
    pool = _FakePool("svc-opsmind")
    request = _make_request(authorization="Bearer rag_x", cookie_owner="u-browser")
    asyncio.run(deps.get_owner_id(request, pool))
    assert request.state.owner_id == "svc-opsmind"


def test_unknown_token_is_401():
    pool = _FakePool(None)
    request = _make_request(authorization="Bearer rag_forged")
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(deps.get_owner_id(request, pool))
    assert excinfo.value.status_code == 401
    assert excinfo.value.headers["WWW-Authenticate"] == "Bearer"


def test_revoked_token_is_indistinguishable_from_unknown():
    """已撤销与不存在对外必须是同一个回答。

    区分开（比如一个 401 一个 403）等于告诉对方「这枚令牌曾经存在过」，
    配合可枚举的输入就是一个探测接口。两者在 SQL 里是同一条 WHERE，
    这条测试钉住的是「以后别有人把撤销单独拆成一个分支」。
    """
    pool = _FakePool(None)
    request = _make_request(authorization="Bearer rag_revoked")
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(deps.get_owner_id(request, pool))
    assert excinfo.value.status_code == 401


def test_no_token_falls_back_to_cookie_identity():
    pool = _FakePool("svc-opsmind")   # 故意给一个会命中的令牌身份，确认根本没走令牌分支
    request = _make_request(cookie_owner="u-browser")
    assert asyncio.run(deps.get_owner_id(request, pool)) == "u-browser"
    assert pool.conn.executed == []   # Cookie 路径不该碰 api_tokens 表


def test_non_bearer_authorization_falls_back_to_cookie():
    """别的 scheme 不当作「令牌无效」拒掉，而是回退 Cookie 身份。

    这样反向代理或浏览器插件塞了一个无关的 Authorization 头时，
    浏览器侧行为完全不变 —— 只有真正带 Bearer 语义的头才走令牌判定。
    """
    pool = _FakePool(None)
    request = _make_request(authorization="Basic abc", cookie_owner="u-browser")
    assert asyncio.run(deps.get_owner_id(request, pool)) == "u-browser"


def test_missing_identity_still_raises():
    """没有令牌、也没有 Cookie 身份时保持改造前行为：当场炸，不兜底生成。"""
    pool = _FakePool(None)
    request = _make_request()
    with pytest.raises(RuntimeError):
        asyncio.run(deps.get_owner_id(request, pool))


# ---- 中间件：什么时候发身份 Cookie ----

def _run_middleware(headers):
    """跑一遍中间件，返回 (放进 state 的字典, 响应头里的 set-cookie 列表)。"""
    captured = {"state": None, "cookies": []}

    async def app(scope, receive, send):
        captured["state"] = dict(scope["state"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def send(message):
        if message["type"] == "http.response.start":
            captured["cookies"] = [
                value.decode("latin-1")
                for key, value in message.get("headers", [])
                if key == b"set-cookie"
            ]

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "scheme": "http", "headers": headers}
    asyncio.run(OwnerCookieMiddleware(app)(scope, receive, send))
    return captured["state"], captured["cookies"]


def test_middleware_skips_identity_for_bearer_calls():
    """带 Bearer 的服务间调用不发身份 Cookie。

    发了也没人用（服务调用不带 Cookie），更糟的是 state 里会多出一个随机身份，
    让「这次请求是谁」出现两个互相矛盾的答案。
    """
    state, cookies = _run_middleware([(b"authorization", b"Bearer rag_x")])
    assert "owner_id" not in state
    assert cookies == []


def test_middleware_issues_identity_for_non_bearer_authorization():
    """别的 Authorization scheme 不改变浏览器侧原有行为：照常发身份。"""
    state, cookies = _run_middleware([(b"authorization", b"Basic abc")])
    assert state.get("owner_id")
    assert len(cookies) == 1


def test_middleware_keeps_cookie_identity_when_bearer_also_present():
    """浏览器同时带了 Cookie 和一个 Bearer 头时，state 仍是 Cookie 身份。

    最终身份由 deps 决定（Bearer 优先），中间件只管别把两个值搞混。
    """
    state, cookies = _run_middleware(
        [(b"authorization", b"Bearer rag_x"), (b"cookie", b"ragent_oid=u-browser")]
    )
    assert state.get("owner_id") == "u-browser"
    assert cookies == []
