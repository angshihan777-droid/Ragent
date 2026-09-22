"""Safe user-facing failure messages. Never send provider bodies/credentials to clients."""
def public_error(error):
    text = str(error or "")
    if text.startswith(("模型不兼容", "模型认证失败", "模型服务限流", "模型响应超时", "模型服务拒绝", "本轮执行未完成", "请先在模型配置", "模型连续返回", "模型返回空")):
        return text
    status = getattr(error, "status_code", None)
    if "Thinking mode" in text or "tool_choice" in text:
        return "模型不兼容强制工具调用，请更新服务后重试。"
    if status in (401, 403) or "AuthenticationError" in text:
        return "模型认证失败，请检查模型配置中的 API Key 和访问权限。"
    if status == 429:
        return "模型服务限流或额度不足，请稍后重试并检查账户额度。"
    if "timeout" in text.lower() or "timed out" in text.lower():
        return "模型响应超时，请稍后重试。"
    if status == 400:
        return "模型服务拒绝请求，请检查模型名称与接口兼容性。"
    if isinstance(error, ValueError) and text.startswith(("请先", "模型连续", "模型返回")):
        return text
    return "本轮执行未完成，请稍后重试；若持续失败，请检查模型配置或服务日志。"
