"""P1 多用户隔离的纯逻辑单测：身份取值/规范化/Cookie 解析/归属判定。

刻意只测纯函数和用假 pool 能驱动的分支，不连真库：这几条逻辑一旦错，
表现都是「功能看着正常但数据串了」，靠手工点页面很难稳定复现，必须由测试钉住。
"""
import asyncio

import pytest
from fastapi import HTTPException
from starlette.responses import Response

from app import config, deps
from app.middleware.owner import (
    OWNER_COOKIE_OVERRIDDEN,
    OwnerCookieMiddleware,
    _read_cookie,
    is_secure_scheme,
    normalize_owner_id,
    set_owner_cookie,
)


# ---- 身份 id 规范化：白名单，不是黑名单 ----

@pytest.mark.parametrize("raw", ["u1", "legacy-u1", "A_b-9", "x" * 64])
def test_normalize_accepts_whitelisted_ids(raw):
    assert normalize_owner_id(raw) == raw


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "x" * 65,           # 超长：Cookie 头不该被一个任意长字符串撑爆
        "a b",              # 空格
        "a;b",              # 分号会把 Cookie 头切成两段
        "a\nb",             # 换行：响应头注入
        "a\tb",
        "../../etc",        # 路径穿越形状
        "用户一",            # 非 ASCII，latin-1 编码 Cookie 头会直接抛错
    ],
)
def test_normalize_rejects_anything_not_whitelisted(raw):
    """非法输入返回 None 而不是「清洗后凑合用」。

    清洗的危险在于两个不同的非法输入可能被洗成同一个合法 id，
    那就是把两个人的数据合进一个身份，比直接拒绝严重得多。
    """
    assert normalize_owner_id(raw) is None

# ---- Secure 标记：本地 http 绝不能加，否则浏览器直接丢掉 Cookie ----

def test_secure_off_for_plain_http():
    assert is_secure_scheme("http", None) is False


def test_secure_on_for_https():
    assert is_secure_scheme("https", None) is True


def test_forwarded_proto_takes_first_hop():
    """反代后面 scheme 是 http，真实协议只在 X-Forwarded-Proto 里。

    取最左一跳：这个头是逗号拼接的链路，最左边才是离浏览器最近的那一段，
    取错会在「浏览器 https → 内网 http」的常见部署下把 Secure 丢掉。
    """
    assert is_secure_scheme("http", "https") is True
    assert is_secure_scheme("http", "https, http") is True
    assert is_secure_scheme("http", "http, https") is False
    assert is_secure_scheme("http", "  HTTPS  ") is True


# ---- Cookie 属性：httpOnly / SameSite / Secure 条件 ----

def test_cookie_attributes():
    """httpOnly 挡 XSS 读取，SameSite=lax 保证顶层跳转仍带身份。"""
    resp = Response()
    set_owner_cookie(resp, "u-42", secure=False)
    raw = resp.headers["set-cookie"]
    assert f"{config.OWNER_COOKIE_NAME}=u-42" in raw
    assert "HttpOnly" in raw
    assert "SameSite=lax" in raw.replace("samesite", "SameSite")
    assert "Path=/" in raw
    # 本地 http 下必须没有 Secure，否则浏览器根本不存这个 Cookie
    assert "Secure" not in raw


def test_cookie_secure_when_https():
    resp = Response()
    set_owner_cookie(resp, "u-42", secure=True)
    assert "Secure" in resp.headers["set-cookie"]


# ---- Cookie 解析：畸形片段不能把身份一起带走 ----

def test_read_cookie_picks_target_key():
    assert _read_cookie("a=1; ragent_oid=u-7; b=2", "ragent_oid") == "u-7"


def test_read_cookie_survives_malformed_neighbours():
    """别的域写了畸形 Cookie 时，我们的身份必须还在。

    SimpleCookie 遇到不合法片段会整串静默丢弃，用户表现是「隔一阵子数据就全没了」，
    且只在特定浏览器特定站点复现。自己切就没有这个连带失效。
    """
    header = 'junk; =novalue; bad"quote"=x; ragent_oid=u-9; trailing'
    assert _read_cookie(header, "ragent_oid") == "u-9"


def test_read_cookie_missing_returns_none():
    assert _read_cookie("a=1; b=2", "ragent_oid") is None
    assert _read_cookie("", "ragent_oid") is None

# ---- 归属判定三分支：不存在 / 存在但不归你 / 归你 ----
#
# 用 asyncio.run 驱动而不是 pytest-asyncio：项目没装那个插件（也不允许为测试升依赖），
# test_graph_logic.py 已经是这个写法，保持一致。

class _FakePool:
    """最小 pool 替身：只支持 async with pool.acquire()，够 _require_owner_match 用。"""

    def acquire(self):
        class _Ctx:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


def _make_resolver(value, calls=None):
    async def resolver(conn, target):
        if calls is not None:
            calls.append(target)
        return value

    return resolver


_OK_UUID = "11111111-1111-1111-1111-111111111111"


def _check(resolver, resource_id, owner_id="u-1"):
    return asyncio.run(deps._require_owner_match(_FakePool(), resolver, resource_id, owner_id))


def test_owner_match_passes_when_owner_is_same():
    assert _check(_make_resolver("u-1"), _OK_UUID) is None


def test_owner_match_404_when_resource_missing():
    """资源不存在与不归你必须是同一个 404。

    若这里回 403，配合可枚举 id 就是一个「探测某个 id 是否真实存在」的接口。
    """
    with pytest.raises(HTTPException) as e:
        _check(_make_resolver(None), _OK_UUID)
    assert e.value.status_code == 404


def test_owner_match_404_when_owner_differs():
    with pytest.raises(HTTPException) as e:
        _check(_make_resolver("u-2"), _OK_UUID)
    assert e.value.status_code == 404


def test_owner_match_404_on_malformed_uuid_not_500():
    """乱填的 id 应当是 404 而不是 500。

    不先收一遍 UUID 的话，asyncpg 会对着 uuid 参数抛 DataError，
    对外表现成服务器错误——等于把「参数写错」报成「后端坏了」。
    """
    calls = []
    with pytest.raises(HTTPException) as e:
        _check(_make_resolver("u-1", calls), "not-a-uuid")
    assert e.value.status_code == 404
    assert calls == []  # 连库都不该碰

# ---- 中间件：什么时候发 Cookie，什么时候不发 ----

def _run_middleware(cookie_header, *, overridden=False):
    """跑一遍中间件，返回 (放进 state 的 owner_id, 响应头里的 set-cookie 列表)。

    直接驱动 ASGI 三元组而不是起 TestClient：这里要断言的就是原始 set-cookie 头有没有被追加，
    经过客户端封装反而看不清「发了几个」。
    """
    captured = {"owner_id": None, "cookies": []}

    async def app(scope, receive, send):
        captured["owner_id"] = scope["state"]["owner_id"]
        if overridden:
            # 模拟「切换身份」端点：自己写了 Cookie，并置标记
            scope["state"][OWNER_COOKIE_OVERRIDDEN] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def send(message):
        if message["type"] == "http.response.start":
            captured["cookies"] = [
                v.decode("latin-1") for k, v in message.get("headers", []) if k == b"set-cookie"
            ]

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "scheme": "http",
        "headers": [(b"cookie", cookie_header.encode("latin-1"))] if cookie_header else [],
    }
    asyncio.run(OwnerCookieMiddleware(app)(scope, receive, send))
    return captured["owner_id"], captured["cookies"]


def test_middleware_issues_identity_when_cookie_absent():
    owner_id, cookies = _run_middleware("")
    assert owner_id  # 新访客当场拿到一个身份
    assert len(cookies) == 1
    assert f"{config.OWNER_COOKIE_NAME}={owner_id}" in cookies[0]


def test_middleware_reuses_existing_cookie_and_does_not_resend():
    """老访客不该每个请求都被重新下发一次 Cookie。

    每次都发不只是白费响应头：一旦哪天生成逻辑出错，就会把用户的身份连带刷掉。
    """
    owner_id, cookies = _run_middleware(f"{config.OWNER_COOKIE_NAME}=u-existing")
    assert owner_id == "u-existing"
    assert cookies == []


def test_middleware_replaces_invalid_cookie_value():
    """Cookie 里的值不合法时按「没有身份」处理，重新发一个。

    否则非法值会一路带到 SQL 参数里，每个请求都查不到数据且没人报错。
    """
    owner_id, cookies = _run_middleware(f"{config.OWNER_COOKIE_NAME}=bad value!")
    assert owner_id != "bad value!"
    assert len(cookies) == 1


def test_middleware_yields_to_explicit_override():
    """切换身份端点自己发了 Cookie 时，中间件必须闭嘴。

    两个同名 Set-Cookie 谁生效取决于浏览器实现，切换身份会变成时好时坏的随机行为。
    """
    _owner_id, cookies = _run_middleware("", overridden=True)
    assert cookies == []