"""提取带来源的文本块；扫描 PDF 和旧 .doc 显式拒绝，不伪造内容。"""
import io
import re
from pathlib import Path

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".md", ".markdown", ".txt")


def text_blocks(text, *, markdown=False):
    blocks, headings, buffer = [], [], []
    fenced = False

    def flush():
        content = "\n".join(buffer).strip()
        if content:
            blocks.append({"text": content, "heading_path": list(headings), "kind": "code" if fenced else "paragraph"})
        buffer.clear()

    for line in text.splitlines():
        if markdown and re.match(r"^\s*(```|~~~)", line):
            if not fenced:
                flush()
                fenced = True
                buffer.append(line)
            else:
                buffer.append(line)
                flush()
                fenced = False
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line) if markdown and not fenced else None
        if heading:
            flush()
            level = len(heading[1])
            headings[:] = headings[:level - 1] + [heading[2].strip()]
            buffer.append(line)
        elif not line.strip() and not fenced:
            flush()
        else:
            buffer.append(line)
    flush()
    return blocks


def parse_file(filename, data):
    ext = Path(filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError("支持 PDF、Markdown、Word（.docx）和 TXT；旧 .doc 请先转换为 .docx")
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            blocks = []
            for page, obj in enumerate(reader.pages, 1):
                text = obj.extract_text() or ""
                if not text.strip():
                    raise ValueError(f"PDF 第 {page} 页没有可提取文本，可能是扫描页；请先 OCR 后上传")
                for block in text_blocks(text):
                    blocks.append({**block, "page_start": page, "page_end": page})
        elif ext == ".docx":
            from docx import Document
            from docx.table import Table
            from docx.text.paragraph import Paragraph
            doc, blocks, headings = Document(io.BytesIO(data)), [], []
            for child in doc.element.body.iterchildren():
                tag = child.tag.rsplit("}", 1)[-1]
                if tag == "p":
                    para = Paragraph(child, doc)
                    text = para.text.strip()
                    style = para.style.name if para.style else ""
                    match = re.search(r"(?:Heading|标题)\s*(\d+)", style, re.I)
                    if match and text:
                        headings = headings[:int(match[1]) - 1] + [text]
                    if text:
                        blocks.append({"text": text, "heading_path": list(headings), "kind": "paragraph"})
                elif tag == "tbl":
                    table = Table(child, doc)
                    rows = [[cell.text.strip().replace("\n", " / ") for cell in row.cells] for row in table.rows]
                    if rows:
                        header = " | ".join(rows[0])
                        for row in rows[1:] or rows[:1]:
                            text = header if len(rows) == 1 else header + "\n" + " | ".join(row)
                            if text.strip(" |\n"):
                                blocks.append({"text": text, "heading_path": list(headings), "kind": "table"})
        else:
            blocks = text_blocks(data.decode("utf-8-sig"), markdown=ext in (".md", ".markdown"))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("文件解析失败，请检查文件是否损坏、加密或编码不是 UTF-8") from exc
    if not blocks:
        raise ValueError("文件解析后没有可用文本")
    return blocks
