def parse_file(path):
    """MVP：解析 txt/md 为纯文本；失败返回 None（调用方负责清理文件，不写 DB）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return None
    if not text.strip():
        return None
    return text
