"""决策范围规则的纯逻辑单测。

这段提示词决定「项目里有资料时，会不会跳过检索直接用模型常识答题」——
它的措辞本身就是行为契约，不是普通文案，所以抽成纯函数在这里钉住。
回归背景：旧措辞把「一般解释」划进 direct，用户上传了 git 笔记之后问「git 是什么」，
模型照着规则选了 direct，检索一步都没跑。
"""
from app.agent.graph import _scope_rule


def test_with_materials_topic_questions_must_retrieve():
    rule = _scope_rule(9)
    # 把数量写进去：模型据此知道资料库非空，不必猜
    assert "9 篇资料" in rule
    # 必须点明「看起来像常识也要查」——这正是旧口径漏掉的那一条
    assert "retrieve" in rule
    assert "常识" in rule


def test_with_materials_only_three_cases_may_answer_directly():
    rule = _scope_rule(1)
    # 白名单要写全，否则模型会把「改写用户粘贴的文本」也当成需要检索的提问
    assert "问候" in rule
    assert "改写" in rule


def test_without_materials_retrieval_is_forbidden():
    rule = _scope_rule(0)
    assert "暂无资料" in rule
    assert "不要选 retrieve" in rule


def test_empty_project_rule_never_leaks_a_count():
    """空资料库时不该出现「已上传 0 篇资料」这种自相矛盾的措辞。"""
    assert "篇资料" not in _scope_rule(0)
