"""Prompt 注入检测：先归一化，再按规则匹配。

边界说明：只拦「指令覆盖 / 提示词套取」这类已知话术，不声称能防语义改写。
归一化先做 NFKC、去零宽字符、转小写、折叠空白，避免全角或零宽拆词绕过。
规则命中只回规则编号，不回显用户原文。
"""
from dataclasses import dataclass
import re
import unicodedata

# 零宽字符常被用来把关键词拆开（ig\u200bnore），匹配前先全部删掉。
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class InjectionVerdict:
    """一次检测的结论：是否拦截、命中的规则编号、归一化后的长度。"""

    blocked: bool
    rule_id: str | None = None
    text_length: int = 0


_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # 英文：覆盖既有指令
    (
        "en.override",
        re.compile(
            r"\b(?:ignore|disregard|forget|override)\s+"
            r"(?:all\s+|any\s+|the\s+)?"
            r"(?:previous|above|prior|earlier|your)?\s*"
            r"(?:instructions?|prompts?|rules?|directives?)\b"
        ),
    ),
    ("en.forget_everything", re.compile(r"\b(?:forget|discard)\s+everything\b")),
    # 英文：切换角色 / 解除限制
    (
        "en.role_switch",
        re.compile(r"\b(?:you\s+are\s+now|from\s+now\s+on,?\s+you\s+(?:are|will\s+be))\b"),
    ),
    # 英文：套取系统提示词
    (
        "en.exfiltrate",
        re.compile(
            r"\b(?:reveal|show|print|output|repeat|dump|leak)\s+(?:me\s+)?"
            r"(?:your|the)\s+(?:system\s+)?(?:prompt|instructions?|rules?|directives?)\b"
        ),
    ),
    ("en.jailbreak", re.compile(r"\b(?:developer|god|dan)\s+mode\b|\bjailbreak\b")),
    # 中文：覆盖既有指令
    (
        "zh.override",
        re.compile(
            r"(?:忽略|无视|忘记|忘掉|不要理会|不遵守)(?:掉)?"
            r"(?:(?:之前|以上|上面|前面)的?(?:所有|全部)?"
            r"|(?:所有|全部)的?(?:之前|以上|上面|前面)?)的?"
            r"(?:指令|要求|提示|规则|设定)"
        ),
    ),
    # 中文：切换角色
    (
        "zh.role_switch",
        re.compile(
            r"(?:从现在(?:开始|起)|接下来)[,，。\s]*(?:你|请)?(?:是|扮演|充当|作为)(?:一个|一名)?"
            r"|你(?:现在)?(?:扮演|充当)(?:一个|一名)?"
        ),
    ),
    # 中文：套取系统提示词
    (
        "zh.exfiltrate",
        re.compile(
            r"(?:输出|显示|打印|告诉我|重复|复述|泄露|透露)(?:一下)?(?:你的|系统)"
            r"(?:系统)?(?:提示词|提示语|指令|设定|规则)"
        ),
    ),
)


def normalize_text(text: str) -> str:
    """把输入收成可匹配的形态；空输入返回空串。"""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_ZERO_WIDTH).lower()
    return _WHITESPACE.sub(" ", text).strip()


def detect_injection(text: str) -> InjectionVerdict:
    """检测一条用户输入；按规则表顺序返回第一条命中。"""
    normalized = normalize_text(text)
    for rule_id, pattern in _RULES:
        if pattern.search(normalized):
            return InjectionVerdict(True, rule_id, len(normalized))
    return InjectionVerdict(False, None, len(normalized))
