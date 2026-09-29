"""对外错误文案：按 openai SDK 异常类型分类，且不泄漏服务端原文。"""
import httpx
import openai
import pytest

from app.services.errors import public_error

_REQ = httpx.Request("POST", "http://llm.test/v1/chat/completions")


def _resp(code):
    return httpx.Response(code, request=_REQ)


@pytest.mark.parametrize("error, expected", [
    (openai.AuthenticationError("secret-body", response=_resp(401), body=None), "模型认证失败"),
    (openai.PermissionDeniedError("secret-body", response=_resp(403), body=None), "模型认证失败"),
    (openai.RateLimitError("secret-body", response=_resp(429), body=None), "模型服务限流"),
    (openai.APITimeoutError(request=_REQ), "模型响应超时"),
    (TimeoutError("provider timeout secret-body"), "模型响应超时"),
    (openai.BadRequestError("secret-body", response=_resp(400), body=None), "模型服务拒绝"),
    (openai.BadRequestError("Thinking mode does not support this tool_choice secret-body",
                            response=_resp(400), body=None), "模型不兼容"),
    (ValueError("请先在模型配置中填写服务地址"), "请先在模型配置"),
    (RuntimeError("boom secret-body"), "本轮执行未完成"),
])
def test_public_error_classifies_without_leaking(error, expected):
    text = public_error(error)
    assert text.startswith(expected)
    assert "secret" not in text


def test_public_error_is_idempotent_for_stored_messages():
    once = public_error(openai.RateLimitError("x", response=_resp(429), body=None))
    assert public_error(once) == once