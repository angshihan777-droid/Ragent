"""引用一致性检查：支持、不支持、缺引用、引用编号不存在。"""
from app.agent.verification import verify_citations
from app.agent import graph


def _source(cid, content):
    return {"citation_id": cid, "content": content}


def test_supported_claim_has_no_warning():
    result = verify_citations(
        "正式员工每年享有十五天带薪年假 [S1]。",
        [_source("S1", "星河公司正式员工每年享有十五天带薪年假。")],
    )
    assert result["checked"] == 1
    assert result["unverified"] == []


def test_unrelated_claim_is_flagged():
    result = verify_citations(
        "公司明年上市发行价一百元 [S1]。",
        [_source("S1", "正式员工每年享有十五天带薪年假。")],
    )
    assert result["checked"] == 1
    assert result["unverified"][0]["overlap"] < 0.35


def test_answer_without_citations_is_not_checked():
    result = verify_citations("这是一句没有引用的普通回答。", [_source("S1", "内容")])
    assert result == {"checked": 0, "unverified": []}


def test_missing_citation_id_is_flagged():
    result = verify_citations("年假有十五天 [S9]。", [_source("S1", "年假有十五天。")])
    assert result["unverified"][0]["missing"] == ["S9"]


def test_multiple_citations_use_union_of_evidence():
    result = verify_citations(
        "年假十五天，住宿上限四百五十元 [S1][S2]。",
        [_source("S1", "正式员工每年享有十五天带薪年假。"),
         _source("S2", "国内出差酒店住宿报销上限为每晚四百五十元。")],
    )
    assert result["unverified"] == []


def test_graph_verify_appends_warning_only_when_needed():
    supported = {"response": "年假十五天 [S1]。", "sources": [_source("S1", "年假十五天。")]}
    assert "未能在引用片段" not in graph._verify(supported)["response"]

    unsupported = {"response": "公司明年上市发行价一百元 [S1]。", "sources": [_source("S1", "年假十五天。")]}
    assert "未能在引用片段" in graph._verify(unsupported)["response"]
