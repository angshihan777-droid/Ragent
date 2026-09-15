"""M8 Skill：给 Agent 挂上一组「可复用的本地能力」，让它按需调用。

为什么要有 Skill：大模型自己算数会算错、也不知道「现在几点」这类实时信息。
把这些确定性能力做成工具交给它，模型只负责「决定要不要用、传什么参数」，
真正的计算/取值由我们的代码执行，结果稳定可控。这就是 function calling 的价值。

为什么用 @tool 装饰器：LangChain 的标准工具协议，函数签名+docstring 会自动
变成给模型看的「工具说明书」，模型据此决定调用，不用我们手写 JSON schema。
"""
import ast
import operator
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

# 只放行「纯算术」用到的运算符：加减乘除、乘方、取模、正负号。
# 白名单式设计是安全关键——绝不用 eval()，避免模型传入恶意表达式执行任意代码。
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float:
    """只递归求值「数字 + 白名单运算符」的表达式树，遇到别的一律拒绝。

    安全关键：整棵语法树逐节点校验，函数调用、变量名、属性访问等全部落到
    else 分支报错，从根上杜绝注入。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("表达式含不允许的元素，只支持数字和 + - * / ** % 运算")


@tool
def calculator(expression: str) -> str:
    """计算一个数学算术表达式并返回结果。支持 + - * / ** % 和括号。

    Args:
        expression: 例如 "3 * (4 + 5)" 或 "2 ** 10"
    """
    tree = ast.parse(expression, mode="eval")
    return str(_safe_eval(tree.body))


@tool
def current_time() -> str:
    """返回当前的日期和时间（东八区，北京时间）。"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.strftime("%Y-%m-%d %H:%M:%S")


# 本地内置技能清单：图构建时把它们绑定给模型。
LOCAL_SKILLS = [calculator, current_time]
