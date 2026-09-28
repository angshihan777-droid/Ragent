"""Safe user-facing failure messages. Never send provider bodies/credentials to clients."""
import asyncio

import openai


def public_error(error):
    text = str(error or "")
    # 已经是安全文案（例如从库里读回的错误）就原样返回，保证函数可以重复调用。
    if text.startswith(("模型不兼容", "模型认证失败", "模型服务限流", "模型响应超时", "模型服务拒绝", "本轮执行未完成", "请先在模型配置", "模型连续返回", "模型返回空")):
        return text
    # 按 openai SDK 的异常类型判断（ChatOpenAI 抛的就是这些），不再从错误字符串里猜。
    # 思考模型拒绝 tool_choice 没有专门的异常类，只能看服务端的错误信息。
    if "Thinking mode" in text or "tool_choice" in text:
        return "模型不兼容强制工具调用，请更新服务后重试。"
    if isinstance(error, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return "模型认证失败，请检查模型配置中的 API Key 和访问权限。"
    if isinstance(error, openai.RateLimitError):
        return "模型服务限流或额度不足，请稍后重试并检查账户额度。"
    if isinstance(error, (openai.APITimeoutError, TimeoutError, asyncio.TimeoutError)):
        return "模型响应超时，请稍后重试。"
    if isinstance(error, openai.BadRequestError):
        return "模型服务拒绝请求，请检查模型名称与接口兼容性。"
    if isinstance(error, ValueError) and text.startswith(("请先", "模型连续", "模型返回")):
        return text
    return "本轮执行未完成，请稍后重试；若持续失败，请检查模型配置或服务日志。"
