# -*- coding: utf-8 -*-
"""把第3课静态课件站点提取为单一 Markdown 文档。仅使用标准库。"""
import html.parser
import re
import os

BASE = os.path.dirname(os.path.abspath(__file__))

ORDER = [
    ("index.html", "概览"),
    ("pages/scope.html", "要做成什么样"),
    ("pages/architecture.html", "系统怎么走"),
    ("pages/security.html", "安全与部署"),
    ("pages/auth-schemes.html", "认证方案对照"),
    ("pages/roadmap.html", "实现路线图"),
    ("pages/s1-skeleton.html", "1 骨架与配置"),
    ("pages/s2-data.html", "2 数据与种子"),
    ("pages/s3-auth.html", "3 登录与会话"),
    ("pages/s4-isolation.html", "4 班级隔离"),
    ("pages/s5-upload.html", "5 上传入库"),
    ("pages/s6-frontend.html", "6 前端页面"),
    ("pages/s7-compose.html", "7 Compose"),
    ("pages/s8-verify.html", "8 验收"),
    ("pages/checklist.html", "核对总表"),
    ("pages/design.html", "设计决策"),
    ("pages/apply.html", "按规约实现"),
    ("pages/ship.html", "提交清单"),
    ("pages/nongoals.html", "明确不做"),
]

SKIP_CLASSES = {"sidebar", "topbar", "steps", "pager", "menu-btn", "crumb", "badge", "brand"}


class Node:
    __slots__ = ("tag", "attrs", "children", "text")

    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []
        self.text = ""

    def cls(self):
        return set(self.attrs.get("class", "").split())


class Builder(html.parser.HTMLParser):
    VOID = {"br", "meta", "link", "img", "hr", "input", "path", "rect", "line", "circle", "marker"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", [])
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag not in self.VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(path):
    with open(path, encoding="utf-8") as f:
        b = Builder()
        b.feed(f.read())
        b.close()
        return b.root


def find_content(node):
    if isinstance(node, Node):
        if node.tag == "main" and "content" in node.cls():
            return node
        for c in node.children:
            r = find_content(c)
            if r is not None:
                return r
    return None


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def inline(node, in_table=False):
    """渲染行内内容（b/strong/code/a/br/文本）。"""
    if isinstance(node, str):
        return node
    tag = node.tag
    if tag in ("b", "strong"):
        t = norm("".join(inline(c, in_table) for c in node.children))
        return f"**{t}**" if t else ""
    if tag == "code":
        t = "".join(inline(c, in_table) for c in node.children)
        return "`" + t.strip() + "`"
    if tag == "a":
        t = norm("".join(inline(c, in_table) for c in node.children))
        href = node.attrs.get("href", "")
        if href.startswith("http"):
            return f"[{t}]({href})"
        return t
    if tag == "br":
        return "<br>" if in_table else "\n"
    if tag in ("span", "i", "em", "small", "u", "sub", "sup", "mark"):
        return "".join(inline(c, in_table) for c in node.children)
    if tag in ("svg", "defs", "marker", "path", "rect", "line"):
        return ""
    return "".join(inline(c, in_table) for c in node.children)


def para(node, in_table=False):
    raw = "".join(inline(c, in_table) for c in node.children)
    if in_table:
        return norm(raw)
    lines = [norm(x) for x in raw.split("\n")]
    return "\n".join(x for x in lines if x)


def svg_texts(node):
    out = []
    if isinstance(node, Node):
        if node.tag == "text":
            t = norm("".join(c if isinstance(c, str) else "" for c in node.children))
            if t:
                out.append(t)
            return out
        for c in node.children:
            out.extend(svg_texts(c))
    return out


def table_md(node):
    head, rows = [], []
    for section in node.children:
        if not isinstance(section, Node) or section.tag not in ("thead", "tbody"):
            continue
        for tr in section.children:
            if not isinstance(tr, Node) or tr.tag != "tr":
                continue
            cells = []
            for cell in tr.children:
                if isinstance(cell, Node) and cell.tag in ("th", "td"):
                    if "tick" in cell.cls():
                        cells.append("☐")
                    else:
                        t = para(cell, in_table=True).replace("|", "\\|")
                        cells.append(t)
            if section.tag == "thead":
                head = cells
            else:
                rows.append(cells)
    if not head and rows:
        head = rows.pop(0)
    n = len(head)
    lines = ["| " + " | ".join(head) + " |", "|" + " --- |" * n]
    for r in rows:
        r += [""] * (n - len(r))
        lines.append("| " + " | ".join(r[:n]) + " |")
    return "\n".join(lines)


def list_md(node, ordered=False, depth=0):
    items = [c for c in node.children if isinstance(c, Node) and c.tag == "li"]
    out = []
    for i, li in enumerate(items, 1):
        inner = []
        nested = []
        for c in li.children:
            if isinstance(c, Node) and c.tag in ("ul", "ol"):
                nested.append(c)
            else:
                inner.append(c)
        text = para(Node("p", []))  # placeholder
        fake = Node("li", [])
        fake.children = inner
        text = para(fake)
        pad = "  " * depth
        mark = f"{i}." if ordered else "-"
        out.append(f"{pad}{mark} {text}")
        for nst in nested:
            out.append(list_md(nst, ordered=(nst.tag == "ol"), depth=depth + 1))
    return "\n".join(out)


def split_title_desc(node, title_tags=("b", "strong")):
    """flow-step / tile 结构：<b>标题</b><span>说明</span> → (标题, 说明)。"""
    title, rest = "", []
    for c in node.children:
        if isinstance(c, Node) and c.tag in title_tags and not title:
            title = para(c)
        else:
            rest.append(c)
    fake = Node("div", [])
    fake.children = rest
    return title, para(fake)


def render(node, out):
    if isinstance(node, str):
        t = norm(node)
        if t:
            out.append(t)
        return
    tag = node.tag
    classes = node.cls()
    if classes & SKIP_CLASSES or tag in ("script", "style", "button"):
        return
    if tag == "h1":
        out.append("## " + para(node))
    elif tag == "h2":
        if "unit-h" in classes:
            num, title = "", ""
            for c in node.children:
                if isinstance(c, Node) and "unit-n" in c.cls():
                    num = para(c)
                elif isinstance(c, Node) and "unit-t" in c.cls():
                    title = para(c)
            out.append(f"### {num}. {title}" if num else "### " + title)
        else:
            out.append("### " + para(node))
    elif tag == "h3":
        # checklist 页的 step-h 里含 “打开该页” 跳转链接，剔除
        if "step-h" in classes:
            kids = [c for c in node.children
                    if not (isinstance(c, Node) and c.tag == "a" and "jump" in c.cls())]
            fake = Node("h3", [])
            fake.children = kids
            out.append("#### " + para(fake))
        else:
            out.append("#### " + para(node))
    elif tag in ("h4", "h5", "h6"):
        out.append("##### " + para(node))
    elif tag == "p":
        t = para(node)
        if not t:
            return
        if "note" in classes:
            out.append("\n".join("> " + x if x else ">" for x in t.split("\n")))
        else:
            out.append(t)
    elif tag == "pre":
        code = "".join(c if isinstance(c, str) else inline(c) for c in node.children)
        code = code.strip("\n")
        code = "\n".join(line.rstrip() for line in code.split("\n"))
        code = "\n".join(line for line in (l.strip() if l.strip() and not l.startswith(" ") else l for l in []))
        # 去掉每行统一的缩进
        lines = [l for l in code.split("\n")]
        indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
        cut = min(indents) if indents else 0
        code = "\n".join(l[cut:] for l in lines)
        out.append("```bash\n" + code + "\n```")
    elif tag == "table":
        out.append(table_md(node))
    elif tag in ("ul", "ol"):
        out.append(list_md(node, ordered=(tag == "ol")))
    elif tag == "figure":
        caption = ""
        labels = svg_texts(node)
        for c in node.children:
            if isinstance(c, Node) and c.tag == "figcaption":
                caption = para(c)
        aria = ""
        for c in node.children:
            if isinstance(c, Node) and c.tag == "svg":
                aria = c.attrs.get("aria-label", "")
        parts = []
        if caption:
            parts.append(caption)
        if labels:
            parts.append("图中标注：" + " / ".join(labels))
        body = "\n".join(parts) if parts else aria
        if body:
            out.append("\n".join("> " + x for x in body.split("\n")))
    elif tag == "div" and "note" in classes:
        t = para(node)
        if t:
            out.append("\n".join("> " + x if x else ">" for x in t.split("\n")))
    elif tag == "div" and "flow" in classes:
        items = []
        for c in node.children:
            if isinstance(c, Node) and "flow-step" in c.cls():
                title, desc = split_title_desc(c)
                items.append(f"**{title}**：{desc}" if desc else f"**{title}**")
        out.append("\n".join(f"{i}. {t}" for i, t in enumerate(items, 1)))
    elif tag == "div" and "grid" in classes:
        items = []
        for c in node.children:
            if isinstance(c, Node) and "tile" in c.cls():
                title, desc = split_title_desc(c)
                items.append(f"- **{title}**：{desc}" if desc else f"- **{title}**")
        out.append("\n".join(items))
    elif tag == "div" and "ask" in classes:
        t = para(node)
        if t:
            out.append("\n".join("> " + x if x else ">" for x in t.split("\n")))
    elif tag in ("section", "article", "div", "main", "body", "html", "root"):
        for c in node.children:
            render(c, out)
    elif tag in ("nav", "aside", "header"):
        return
    else:
        t = para(node)
        if t:
            out.append(t)


def convert(rel):
    root = parse(os.path.join(BASE, rel))
    content = find_content(root)
    out = []
    render(content, out)
    # 合并多余空行由 join 处理；此处过滤空块
    return [b for b in (b.strip("\n") for b in out) if b.strip()]


def main():
    doc = [
        "# 第 3 课：认证授权与知识库入库",
        "",
        "> 来源：北京大学《互联网软件开发技术与实践》第 3 课课件（HTML 整理为 Markdown）",
    ]
    for rel, name in ORDER:
        blocks = convert(rel)
        doc.append("---")
        doc.extend(blocks)
        print(f"{rel}: {len(blocks)} blocks")
    text = "\n\n".join(doc) + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    with open(os.path.join(BASE, "第3课.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print("written", len(text), "chars")


if __name__ == "__main__":
    main()
