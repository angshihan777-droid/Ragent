"""引用一致性检查：轻量幻觉检测。

边界：只看「带引用编号的句子」和「被引用片段」的词面重叠，
不调用模型做语义判断。它能抓住「引用了一个完全不相关的片段」，
但抓不住同义改写或引用正确片段却推错结论的情况。
"""
import re

_CITATION = re.compile(r"\[S(\d+)\]")
_SENTENCE = re.compile(r"[^。！？.!?\n]+[。！？.!?]?")
_WORD = re.compile(r"[a-z0-9_]+")
_ZH_RUN = re.compile(r"[\u4e00-\u9fff]+")
_STOP = set("的了是在和与及或对把被为这那有也就都而及其一个我们你们他们它不没很更最可以需要应该")


def _tokens(text: str) -> set[str]:
    """英文按词、中文按单字 + 双字切；去掉高频停用词。"""
    text = (text or "").lower()
    tokens = set(_WORD.findall(text))
    for run in _ZH_RUN.findall(text):
        tokens.update(run)
        tokens.update(run[i:i + 2] for i in range(len(run) - 1))
    return {token for token in tokens if token not in _STOP}


def verify_citations(answer: str, sources: list[dict], threshold: float = 0.35) -> dict:
    """逐句检查引用依据，返回检查数与未验证结论。"""
    by_id = {
        str(source.get("citation_id")): source.get("content", "")
        for source in sources
        if source.get("citation_id")
    }
    checked = 0
    unverified = []
    for sentence in _SENTENCE.findall(answer or ""):
        citation_ids = _CITATION.findall(sentence)
        if not citation_ids:
            continue
        claim = _CITATION.sub("", sentence).strip()
        claim_tokens = _tokens(claim)
        if len(claim_tokens) < 4:
            continue
        checked += 1
        cited = [f"S{cid}" for cid in citation_ids]
        missing = [cid for cid in cited if cid not in by_id]
        evidence_tokens = set()
        for cid in cited:
            evidence_tokens |= _tokens(by_id.get(cid, ""))
        overlap = len(claim_tokens & evidence_tokens) / max(1, len(claim_tokens))
        if missing or overlap < threshold:
            unverified.append({
                "claim": claim[:200],
                "citations": cited,
                "overlap": round(overlap, 3),
                "missing": missing,
            })
    return {"checked": checked, "unverified": unverified}
