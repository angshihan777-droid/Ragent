"""Provider-neutral structured output: JSON mode, strict schema, one repair attempt."""
import json
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError


async def invoke_json(model, schema, messages, config=None):
    contract = SystemMessage(content=(
        "Return only a JSON object matching this JSON Schema. No markdown or reasoning.\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    ))
    prompt = [contract, *messages]
    for attempt in range(2):
        # No tools/tool_choice: compatible with thinking models that reject forced tools.
        # 传入 config：让图的回调（事件流、token 用量统计）也能看到这次调用
        response = await model.bind(response_format={"type": "json_object"}).ainvoke(prompt, config)
        try:
            return schema.model_validate_json(response.content, strict=True)
        except (ValidationError, TypeError):
            if attempt:
                raise ValueError("模型连续返回无效结构，请重试或检查模型兼容性") from None
            prompt = [*prompt, HumanMessage(content="上次输出不符合约定。请重新生成完整 JSON，严格遵守字段类型与长度限制。")]
