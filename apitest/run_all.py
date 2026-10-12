"""一键接口测试：起临时实例（临时库 + stub 网关 + Qdrant），跑全部用例，出 HTML 报告。

用法（仓库根目录）：
    python apitest/run_all.py

报告写入 apitest/reports/（已 gitignore）。依赖：Qdrant（默认 http://localhost:6333，
不可达时尝试用 docker 临时起一个）；嵌入/对话网关由内置 stub 扮演。
"""

import datetime
import html
import importlib.util
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
from http.server import HTTPServer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")


def qdrant_reachable():
    try:
        urllib.request.urlopen(f"{QDRANT_URL}/collections", timeout=2)
        return True
    except Exception:
        return False


def ensure_qdrant():
    if qdrant_reachable():
        return None
    print("[apitest] Qdrant 不可达，尝试 docker 临时容器 campusclaw-apitest-qdrant ...")
    subprocess.run(["docker", "run", "-d", "--name", "campusclaw-apitest-qdrant",
                    "-p", "127.0.0.1:6333:6333", "qdrant/qdrant:v1.13.4"],
                   capture_output=True)
    for _ in range(30):
        if qdrant_reachable():
            return "campusclaw-apitest-qdrant"
        time.sleep(1)
    raise RuntimeError("Qdrant 不可用且 docker 启动失败；请先启动 Qdrant 或 Docker Desktop")


def start_stub_gateway():
    from scripts.dev_stub_gateway import Handler
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


def start_app(base_url_port):
    from app import create_app
    from werkzeug.serving import make_server
    app = create_app()
    server = make_server("127.0.0.1", base_url_port, app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def discover_cases():
    cases_dir = os.path.join(ROOT, "apitest", "cases")
    found = []
    for dirpath, _, files in os.walk(cases_dir):
        for f in sorted(files):
            if f.endswith(".py") and f[:-3].isupper():
                rel = os.path.relpath(os.path.join(dirpath, f), cases_dir)
                parts = rel[:-3].split(os.sep)
                method, path = parts[-1], "/" + "/".join(parts[:-1])
                found.append((method, path, os.path.join(dirpath, f)))
    return sorted(found, key=lambda x: (x[1], x[0]))


def load_case(path):
    spec = importlib.util.spec_from_file_location(
        "case_" + os.path.basename(os.path.dirname(path)) + "_" + os.path.basename(path),
        path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def render_html(results, path, started):
    rows = []
    total = passed = 0
    for r in results:
        ok_all = r["ok"]
        total += 1
        passed += ok_all
        checks = "".join(
            f'<tr class="{"ok" if ok else "bad"}"><td>{"✓" if ok else "✗"}</td>'
            f"<td>{html.escape(desc)}</td><td>{html.escape(str(detail))}</td></tr>"
            for desc, ok, detail in r["checks"])
        rows.append(
            f'<h3 class="{"ok" if ok_all else "bad"}">{r["method"]} {html.escape(r["path"])} '
            f'— {"通过" if ok_all else "失败"}（{r["duration"]:.1f}s）</h3>'
            f"<table>{checks}</table>"
            + (f'<pre class="bad">{html.escape(r["error"])}</pre>' if r.get("error") else ""))
    doc = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>CampusClaw 接口测试报告</title><style>
body {{ font-family: "Microsoft YaHei", sans-serif; max-width: 900px; margin: 24px auto; padding: 0 16px; }}
h1 {{ border-bottom: 2px solid #8a1717; padding-bottom: 8px; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 18px; font-size: 13px; }}
td {{ border: 1px solid #ddd; padding: 4px 8px; }}
.ok {{ color: #1a7f37; }} .bad {{ color: #b00020; }}
pre.bad {{ background: #fff5f5; padding: 8px; white-space: pre-wrap; }}
</style></head><body>
<h1>CampusClaw 接口测试报告</h1>
<p>时间：{started} ｜ 用例 {total} 个，通过 {passed}，失败 {total - passed}</p>
{''.join(rows)}
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    tmp = tempfile.mkdtemp(prefix="campusclaw-apitest-")
    os.environ["DATABASE"] = os.path.join(tmp, "app.db")
    os.environ["UPLOAD_DIR"] = os.path.join(tmp, "uploads")
    os.environ["SECRET_KEY"] = "apitest-secret"

    qdrant_container = ensure_qdrant()
    stub = start_stub_gateway()
    os.environ.update({
        "EMBEDDING_API_BASE": stub, "EMBEDDING_API_KEY": "apitest",
        "EMBEDDING_MODEL": "stub-embed", "CHAT_API_BASE": stub,
        "CHAT_API_KEY": "apitest", "CHAT_MODEL": "stub-chat",
    })

    import scripts.init_db as init_db
    init_db.main()

    server = start_app(0)  # noqa: F841 — 端口 0 由系统分配
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    print(f"[apitest] 临时实例 {base_url}，库 {os.environ['DATABASE']}")

    from apitest.lib import Ctx
    results = []
    started = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for method, path, file in discover_cases():
        ctx = Ctx(base_url, os.environ["DATABASE"])
        t0 = time.time()
        error = ""
        try:
            load_case(file).run(ctx)
        except Exception:
            error = traceback.format_exc()
        ok = all(ok for _, ok, _ in ctx.checks) and not error
        results.append({"method": method, "path": path, "checks": ctx.checks,
                        "ok": ok, "error": error, "duration": time.time() - t0})
        print(f"  {'PASS' if ok else 'FAIL'}  {method} {path} "
              f"({sum(1 for _, o, _ in ctx.checks if o)}/{len(ctx.checks)} 检查通过)")

    os.makedirs(os.path.join(ROOT, "apitest", "reports"), exist_ok=True)
    report = os.path.join(ROOT, "apitest", "reports",
                          "report-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".html")
    render_html(results, report, started)

    if qdrant_container:
        subprocess.run(["docker", "rm", "-f", qdrant_container], capture_output=True)
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    print(f"[apitest] {passed}/{total} 用例通过，报告：{report}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
