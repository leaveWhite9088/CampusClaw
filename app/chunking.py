"""正文切分：auto / custom / hierarchy 三种策略。

输出切片含 chunk_text、chunk_index、start_offset、end_offset；
偏移量相对于（可能经过预处理的）待切分文本，而非原始文件。
切分模块不调用嵌入服务，也不写入向量库。
"""

import re

AUTO_MAX_LEN = 800
AUTO_OVERLAP = 80
CUSTOM_MIN_LEN = 100
CUSTOM_MAX_LEN = 2000

_URL_RE = re.compile(r"https?://\S+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_WS_RE = re.compile(r"\s+")
_HEADING_RE = re.compile(r"^#{1,3}\s", re.MULTILINE)

# 断点优先级：空行 > 换行 > 句号
_BREAK_CHARS = ["\n\n", "\n", "。"]


class ChunkingError(ValueError):
    pass


def preprocess(text, strip_links=False, collapse_whitespace=False):
    """预处理仅作用于待切分/待嵌入文本，不改写库中原文。"""
    if strip_links:
        text = _URL_RE.sub("", text)
        text = _EMAIL_RE.sub("", text)
    if collapse_whitespace:
        text = _WS_RE.sub(" ", text)
    return text


def _window_chunks(text, max_len, overlap):
    """窗口切分：优先在空行/换行/句号处断开，无断点按 max_len 强制截断。"""
    if max_len <= 0 or overlap < 0 or overlap >= max_len:
        raise ChunkingError("非法窗口参数")
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_len, n)
        if end < n:
            # 在窗口后半段找最佳断点，避免把句子截在窗口边界
            window = text[start:end]
            cut = -1
            for marker in _BREAK_CHARS:
                pos = window.rfind(marker, max_len // 2)
                if pos != -1:
                    cut = pos + len(marker)
                    break
            if cut > 0:
                end = start + cut
        piece = text[start:end]
        if piece.strip():
            chunks.append((start, end, piece))
        if end >= n:
            break
        start = end - overlap
    return chunks


def _hierarchy_sections(text):
    """按 #/##/### 分章，标题保留在该章文本内。返回 (start, end, section_text)。"""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [(0, len(text), text)]
    sections = []
    if matches[0].start() > 0:
        sections.append((0, matches[0].start(), text[: matches[0].start()]))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((m.start(), end, text[m.start():end]))
    return sections


def chunk_text(text, strategy="auto", max_len=None, overlap_ratio=None,
               strip_links=False, collapse_whitespace=False):
    """按策略切分正文，返回 [{'chunk_index','chunk_text','start_offset','end_offset'}]。

    - auto：固定 800 字/重叠 80，忽略另行填写的长度与预处理参数
    - custom：最大长度 100–2000、重叠 0–50%，可选预处理
    - hierarchy：Markdown 标题分章，过长章再按 auto 窗口
    """
    if not text or not text.strip():
        return []

    if strategy == "auto":
        work = text
        pieces = _window_chunks(work, AUTO_MAX_LEN, AUTO_OVERLAP)
    elif strategy == "custom":
        limit = max_len if max_len is not None else AUTO_MAX_LEN
        if not (CUSTOM_MIN_LEN <= limit <= CUSTOM_MAX_LEN):
            raise ChunkingError("custom 策略最大长度须在 100–2000 之间")
        ratio = overlap_ratio if overlap_ratio is not None else 0.1
        if not (0.0 <= ratio <= 0.5):
            raise ChunkingError("custom 策略重叠比例须在 0–50% 之间")
        work = preprocess(text, strip_links=strip_links,
                          collapse_whitespace=collapse_whitespace)
        pieces = _window_chunks(work, limit, int(limit * ratio))
    elif strategy == "hierarchy":
        work = text
        pieces = []
        for sec_start, sec_end, sec_text in _hierarchy_sections(work):
            if len(sec_text) <= AUTO_MAX_LEN:
                if sec_text.strip():
                    pieces.append((sec_start, sec_end, sec_text))
            else:
                for off_start, off_end, piece in _window_chunks(sec_text, AUTO_MAX_LEN, AUTO_OVERLAP):
                    pieces.append((sec_start + off_start, sec_start + off_end, piece))
    else:
        raise ChunkingError(f"未知切分策略: {strategy}")

    return [
        {
            "chunk_index": i,
            "chunk_text": piece,
            "start_offset": start,
            "end_offset": end,
        }
        for i, (start, end, piece) in enumerate(pieces)
    ]
