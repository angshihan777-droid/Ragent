"""身份 Cookie 的读取与下发。

职责边界：本文件只管「这次请求属于谁」这一个问题——从 Cookie 取身份，没有就新发一个。
它不做任何归属校验，校验在 deps.py；这样中间件保持无状态、不碰数据库，
每个请求少一次 IO，也不会因为库抖动把首页整个打挂。

为什么写成裸 ASGI 中间件而不用 BaseHTTPMiddleware：本项目的流式回答是长连 SSE
（/requests/{id}/stream 可以挂几十秒），BaseHTTPMiddleware 会把响应再包一层
StreamingResponse 并接管 http.disconnect，长连下客户端关标签页的取消信号可能传不到
生成器，留下一直在跑的协程。裸中间件只在 http.response.start 上插一个响应头，
响应体一个字节都不经手，SSE 链路的行为与改造前完全一致。

⚠️ 这是隔离，不是鉴权：谁拿到 Cookie 里的值就等于那个人。清 Cookie / 换浏览器 /
无痕模式都等于一个全新的空白身份——旧数据仍在库里，但再也访问不到（除非手动切换身份）。
"""
import re
import uuid

from starlette.datastructures import Headers
from starlette.responses import Response

from app.config import OWNER_COOKIE_MAX_AGE, OWNER_COOKIE_NAME

# Cookie 值是不可信输入，先按白名单收窄再用。放行 uuid4 与 legacy-u1 这类连字符形式。
# 为什么要校验：这个值会进日志、会被原样写回 Set-Cookie 头，
# 虽然 SQL 走参数化挡住了注入，但含控制字符的值能污染响应头。
_OWNER_ID_PATTERN = re.compile(r"\A[A-Za-z0-9_-]{1,64}\Z")

# 端点自己覆写了 Cookie 时（切换身份），用这个键告诉中间件别再盖回去。
# 不加这个标记，切换身份的响应会同时带两个 Set-Cookie: ragent_oid，
# 浏览器取后一个，结果切换时好时坏——完全取决于谁的头写在后面。
OWNER_COOKIE_OVERRIDDEN = "owner_cookie_overridden"


def normalize_owner_id(raw: str | None) -> str | None:
    """把 Cookie 原值收成可用的身份 id；不合法返回 None，由调用方决定新发一个。"""
    if not raw:
        return None
    return raw if _OWNER_ID_PATTERN.match(raw) else None


def is_secure_scheme(scheme: str, forwarded_proto: str | None) -> bool:
    """判断浏览器那一跳是否 HTTPS，决定 Cookie 加不加 Secure。

    为什么必须条件加而不是一律加：Secure Cookie 在 http 上会被浏览器直接丢弃，
    本地 http://localhost:5173 开发态一律加 Secure 等于身份永远存不下来，
    表现是「每次刷新都是新用户」，很难往 Cookie 属性上联想。

    同时认 X-Forwarded-Proto：部署在反代后面时到应用这一跳是 http，
    但浏览器那一跳是 https，只看 scope["scheme"] 会漏加 Secure。
    """
    if forwarded_proto:
        # 反代可能串联多层，取最左边那一跳（最接近浏览器的协议）
        return forwarded_proto.split(",")[0].strip().lower() == "https"
    return scheme == "https"


def set_owner_cookie(response: Response, owner_id: str, *, secure: bool) -> None:
    """统一的 Cookie 下发口径：中间件与「切换身份」端点都走这里，属性不会写歪。"""
    response.set_cookie(
        OWNER_COOKIE_NAME,
        owner_id,
        max_age=OWNER_COOKIE_MAX_AGE,
        # httpOnly：JS 读不到，XSS 偷不走凭证
        httponly=True,
        # Lax 而非 Strict：Strict 会让「从外部链接点进来」的首个请求不带 Cookie，
        # 表现成偶发的空列表。本项目没有跨站写操作，Lax 足够。
        samesite="lax",
        path="/",
        secure=secure,
    )


def _cookie_header_value(owner_id: str, *, secure: bool) -> str:
    """借一个空 Response 拼出 Set-Cookie 的值，不手写属性串。

    复用 starlette 的 set_cookie 是为了避免自己拼 Max-Age/SameSite 时写错格式——
    Cookie 属性写错不会报错，只会静默不生效，正是最难查的那类问题。
    """
    probe = Response()
    set_owner_cookie(probe, owner_id, secure=secure)
    return probe.headers["set-cookie"]


class OwnerCookieMiddleware:
    """确保每个请求都有身份：Cookie 里没有就当场生成一个并随响应下发。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # websocket / lifespan 不涉及身份，原样放过，不去碰它们的消息流
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        raw_cookie = headers.get("cookie", "")
        owner_id = normalize_owner_id(_read_cookie(raw_cookie, OWNER_COOKIE_NAME))
        issued = owner_id is None
        if issued:
            owner_id = str(uuid.uuid4())

        # 放进 scope["state"] 供依赖读取（即 request.state）：deps 只读 state，
        # 不重复解析 Cookie，保证同一请求内「新发的身份」与「写回浏览器的身份」是同一个值。
        state = scope.setdefault("state", {})
        state["owner_id"] = owner_id
        secure = is_secure_scheme(scope.get("scheme", "http"), headers.get("x-forwarded-proto"))

        async def send_wrapper(message):
            # 只在新发身份时写 Set-Cookie：每个请求都带一次是白费响应头，
            # 更重要的是会把「切换身份」端点刚写好的值盖掉。
            if (
                message["type"] == "http.response.start"
                and issued
                and not state.get(OWNER_COOKIE_OVERRIDDEN)
            ):
                message.setdefault("headers", [])
                message["headers"].append(
                    (b"set-cookie", _cookie_header_value(owner_id, secure=secure).encode("latin-1"))
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _read_cookie(cookie_header: str, name: str) -> str | None:
    """从 Cookie 头里取一个键。

    自己切而不用 SimpleCookie：SimpleCookie 遇到不合法的 Cookie 片段会整串静默丢弃，
    同一个浏览器里只要有另一个域写了畸形 Cookie，我们的身份就会跟着一起消失。
    """
    for part in cookie_header.split(";"):
        key, _, value = part.partition("=")
        if key.strip() == name:
            return value.strip()
    return None