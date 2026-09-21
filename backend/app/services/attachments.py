"""附件解析：把上传的 PDF/Word/Markdown/纯文本抽成纯文本，供 RAG 切块入库。

解析库(pypdf/python-docx)只在真正解析对应类型时惰性 import——
大多数请求不上传文件，惰性加载避免无谓拖慢进程启动与内存占用。
"""
from __future__ import annotations

# 支持的后缀：与前端 accept 保持一致，未知类型直接拒绝而不是猜测。
SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".md", ".markdown", ".txt")


def _ext(filename: str) -> str:
    """取小写扩展名（含点），无扩展名返回空串。"""
    name = filename or ""
    dot = name.rfind(".")
    return name[dot:].lower() if dot != -1 else ""


def parse_file(filename: str, data: bytes) -> str:
    """按扩展名把上传文件解析成纯文本；不支持的类型显式报错。

    预设不成立(空文件/无法解析)时直接抛错，由路由收成 400，
    不把"没解析出内容"伪装成入库成功。
    """
    ext = _ext(filename)
    if ext == ".pdf":
        text = _parse_pdf(data)
    elif ext == ".docx":
        text = _parse_docx(data)
    elif ext in (".md", ".markdown", ".txt"):
        # 文本类直接按 UTF-8 读，非法字节用替换字符兜底而不是整体失败
        text = data.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"不支持的文件类型: {ext or '(无扩展名)'}")
    text = text.strip()
    if not text:
        raise ValueError("文件解析后没有可用文本")
    return text


def _parse_pdf(data: bytes) -> str:
    """逐页抽取 PDF 文本；扫描件(无文本层)会得到空串，由上层报错。"""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n\n".join(pages)


def _parse_docx(data: bytes) -> str:
    """抽取 .docx 的段落文本；不处理表格/图片等复杂结构，取正文够检索用。"""
    import io

    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(para.text for para in doc.paragraphs)
