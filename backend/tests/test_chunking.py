"""切块：按真实 token 数切、不跨标题合并、保留溯源元数据。"""
from tokenizers import Tokenizer, models, pre_tokenizers

from app.services.chunking import split_blocks


def _char_tokenizer():
    # 每个字符一个 token：测试里 token 数 = 字符数，便于断言，不用下载真实模型
    chars = "".join(chr(c) for c in range(32, 127)) + "年假天数病假规则流程说明第一二三四五六七八九十。，\n"
    tok = Tokenizer(models.WordLevel({c: i for i, c in enumerate(dict.fromkeys(chars + "[UNK]"))}, unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.Split("", behavior="isolated")
    return tok


def _count(tok, text):
    return len(tok.encode(text, add_special_tokens=False).ids)


def test_chunks_respect_token_budget_and_keep_order():
    tok = _char_tokenizer()
    blocks = [{"text": "年假规则。" * 60, "heading_path": ["年假"], "kind": "paragraph"}]
    chunks = split_blocks(blocks, tok, title="说明", max_tokens=64)
    assert len(chunks) > 1
    assert all(_count(tok, c["content"]) <= 64 for c in chunks)
    assert [c["metadata"]["chunk_index"] for c in chunks] == list(range(len(chunks)))


def test_chunks_carry_title_and_heading_prefix():
    tok = _char_tokenizer()
    chunks = split_blocks([{"text": "病假流程", "heading_path": ["病假"], "kind": "paragraph"}], tok, title="说明")
    assert chunks[0]["content"].startswith("说明 / 病假")
    assert chunks[0]["metadata"]["heading_path"] == ["病假"]


def test_blocks_under_different_headings_are_not_merged():
    tok = _char_tokenizer()
    blocks = [{"text": "年假天数", "heading_path": ["年假"], "kind": "paragraph"},
              {"text": "病假规则", "heading_path": ["病假"], "kind": "paragraph"}]
    chunks = split_blocks(blocks, tok)
    assert len(chunks) == 2


def test_adjacent_blocks_under_same_heading_are_merged():
    tok = _char_tokenizer()
    blocks = [{"text": "年假天数", "heading_path": ["年假"], "kind": "paragraph"},
              {"text": "年假流程", "heading_path": ["年假"], "kind": "paragraph"}]
    chunks = split_blocks(blocks, tok)
    assert len(chunks) == 1 and chunks[0]["metadata"]["block_end"] == 1