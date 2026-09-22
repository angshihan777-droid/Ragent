"""结构优先、token 有界的切分；元数据中的 offsets 对应 block_start 至 block_end 合并后的文本。"""
import re

INDEX_VERSION = 2
TARGET_TOKENS = 384
OVERLAP_TOKENS = 48


def split_blocks(blocks, tokenizer, title="", max_tokens=TARGET_TOKENS):
    def tokens(text):
        return tokenizer.encode(text, add_special_tokens=False)

    def clip(text, limit):
        encoded = tokens(text)
        return text if len(encoded.ids) <= limit else text[:encoded.offsets[limit - 1][1]]

    chunks = []
    # 相邻、同来源的短段落先合并；不跨页/标题合并，保证可追溯。
    groups = []
    for index, block in enumerate(blocks):
        text = block["text"].strip()
        if not text:
            continue
        key = (tuple(block.get("heading_path", [])), block.get("page_start"), block.get("kind"))
        if groups and groups[-1]["key"] == key and len(tokens(groups[-1]["text"] + "\n\n" + text).ids) <= max_tokens - 64:
            groups[-1]["text"] += "\n\n" + text
            groups[-1]["block_end"] = index
        else:
            groups.append({**block, "text": text, "key": key, "block_start": index, "block_end": index})
    for block in groups:
        prefix = clip(" / ".join([title, *block.get("heading_path", [])]).strip(" /"), 48)
        prefix = prefix + "\n\n" if prefix else ""
        budget = max_tokens - len(tokens(prefix).ids) - 4
        text, start = block["text"], 0
        while start < len(text):
            remaining = text[start:]
            encoded = tokens(remaining)
            if not encoded.ids:
                break
            end = len(text) if len(encoded.ids) <= budget else start + encoded.offsets[budget - 1][1]
            if end < len(text):
                boundaries = list(re.finditer(r"[。！？!?；;\n]|\.(?=\s)", text[start:end]))
                if boundaries and boundaries[-1].end() >= (end - start) * 0.6:
                    end = start + boundaries[-1].end()
            content = prefix + text[start:end]
            # 拼接前后 token 边界可能改变，最后再校验一次实际输入预算。
            while len(tokens(content).ids) > max_tokens and end > start + 1:
                end -= 1
                content = prefix + text[start:end]
            metadata = {k: block[k] for k in ("heading_path", "page_start", "page_end", "kind", "block_start", "block_end") if k in block}
            metadata.update(index_version=INDEX_VERSION, chunk_index=len(chunks), start_offset=start, end_offset=end)
            chunks.append({"content": content, "metadata": metadata})
            if end >= len(text):
                break
            span = tokens(text[start:end])
            overlap = min(OVERLAP_TOKENS, max(0, len(span.ids) // 4))
            next_start = start + span.offsets[-overlap][0] if overlap else end
            start = next_start if next_start > start else end
    return chunks
