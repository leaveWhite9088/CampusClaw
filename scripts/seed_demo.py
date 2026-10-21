"""演示数据 seed：为第 6 课验收准备可复现的演示场景（在 app 容器内执行）。

    docker compose exec app python scripts/seed_demo.py

步骤：
1. 上传 A 班材料「数学自习笔记」（含去括号/单位换算/分数三节，切分后 3 个切片）；
2. 登记并连接本班 MCP 服务器 campus-tools（Base URL http://mcp-server:8090，令牌取
   环境变量 MCP_AUTH_TOKEN，与 mcp-server 容器一致），发现工具缓存；
3. 创建技能「数学解题引导」（工具白名单含 knowledge_search 与 MCP 引用）；
4. 创建内置之外的应用「数学工具助手」，绑定该技能与上述材料。
幂等：按名称判重，重复执行不产生重复数据。连接失败仅告警不中断（可用后重跑）。
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MATH_MATERIAL = """# 数学自习笔记

## 去括号与合并同类项

去括号法则：括号前面是加号时，去掉括号和括号前的加号，括号里各项都不变号；括号前面是减号时，去掉括号和括号前的减号，括号里每一项都要变号。
合并同类项时，把系数相加，字母和字母的指数不变。
例：化简 (3a + 2b) - (a - b) = 3a + 2b - a + b = 2a + 3b。
常见错误：只给第一项乘系数、漏掉变号。检查方法是数一数括号内有几项，展开后就应该有几项。

## 常用单位换算

长度单位从大到小：千米（km）、米（m）、分米（dm）、厘米（cm）、毫米（mm），相邻单位之间进率是 10。
1 千米 = 1000 米，1 米 = 100 厘米，1 米 = 1000 毫米。
质量单位：1 吨 = 1000 千克，1 千克 = 1000 克。
时间单位：1 时 = 60 分，1 分 = 60 秒。
换算方法：大单位化小单位乘进率，小单位化大单位除以进率。

## 分数与方程

把单位 1 平均分成若干份，表示这样一份或几份的数叫分数。
异分母分数相加减，要先通分：取几个分母的最小公倍数作公分母，再按同分母分数加减。
含有未知数的等式叫方程。解方程时利用等式的性质：两边同时加减同一个数，或同时乘除同一个非零数，等式仍然成立。
解完方程要检验：把结果代回原方程，看左右两边是否相等。
"""


def main():
    from app import create_app
    from app import mcp
    from app.db import (
        create_app_row, create_mcp_server, create_skill, get_conn,
        get_entry_for_material, get_mcp_server_by_name, list_mcp_tools,
        replace_mcp_tools, set_mcp_connected, update_skill,
    )
    from app.skillfile import validate_tool_refs

    app = create_app()
    with app.app_context():
        conn = get_conn()
        try:
            class_a = conn.execute(
                "SELECT id FROM classes WHERE name = '班级 A'").fetchone()["id"]
            teacher_id = conn.execute(
                "SELECT id FROM users WHERE username = 'teacher_a'").fetchone()["id"]
            template_id = conn.execute(
                "SELECT id FROM prompt_templates WHERE class_id = ? AND name = '解题引导模板'",
                (class_a,)).fetchone()["id"]
        finally:
            conn.close()

        # 1. 材料（幂等）
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT m.id FROM materials m JOIN knowledge_entries e ON e.material_id = m.id "
                "WHERE m.class_id = ? AND m.title = 'A 班·数学自习笔记'",
                (class_a,)).fetchone()
        finally:
            conn.close()
        if row is None:
            from app.db import insert_material_with_knowledge
            material_id = insert_material_with_knowledge(
                class_id=class_a, title="A 班·数学自习笔记",
                filename="a_math_notes.md", file_path=None,
                uploaded_by=teacher_id, body_text=MATH_MATERIAL)
            entry = get_entry_for_material(material_id)
            from app.indexing import index_entry
            chunk_ids, _, embedded = index_entry(entry["id"], strategy="auto")
            print(f"[seed] 材料已入库并索引：{len(chunk_ids)} 个切片（embedded={embedded}）")
        else:
            material_id = row["id"]
            print(f"[seed] 材料已存在（id={material_id}），跳过")

        # 2. MCP 服务器登记 + 连接发现（幂等；失败告警不中断）
        server = get_mcp_server_by_name(class_a, "campus-tools")
        token = os.environ.get("MCP_AUTH_TOKEN", "")
        base_url = os.environ.get("DEMO_MCP_BASE_URL", "http://mcp-server:8090")
        if server is None:
            server_id = create_mcp_server(class_a, "campus-tools", base_url, token)
            print(f"[seed] 已登记 MCP 服务器 campus-tools → {base_url}")
        else:
            server_id = server["id"]
        try:
            mcp.json_rpc(base_url, "initialize",
                         {"protocolVersion": "2024-11-05",
                          "clientInfo": {"name": "campusclaw", "version": "1.0"}}, token)
            result = mcp.json_rpc(base_url, "tools/list", {}, token)
            tools = result.get("tools", [])
            replace_mcp_tools(server_id, tools)
            set_mcp_connected(server_id, 1)
            print(f"[seed] 连接成功，发现工具：{[t['name'] for t in tools]}")
        except mcp.McpError as e:
            print(f"[seed] 警告：MCP 连接失败（{e}）；后续可重新执行本脚本或在页面重试连接")

        # 3. 数学解题引导技能（幂等；工具引用按保存时同一套校验）
        skill_name = "数学解题引导"
        conn = get_conn()
        try:
            row = conn.execute("SELECT id FROM skills WHERE class_id = ? AND name = ?",
                               (class_a, skill_name)).fetchone()
        finally:
            conn.close()
        tools_refs = "knowledge_search, formula_hint@campus-tools, unit_convert@campus-tools"
        refs = ["knowledge_search", "formula_hint@campus-tools", "unit_convert@campus-tools"]
        err = validate_tool_refs(class_a, refs)
        if err:
            print(f"[seed] 警告：MCP 工具校验未通过（{err}）；技能将以停用状态创建")
        if row is None:
            instructions = (
                "你是数学解题引导助手。规则：1) 先判断题目考查的知识点，再给一条公式或法则提示；"
                "2) 只指出下一步该检查什么，不直接给出最终答案；"
                "3) 涉及单位换算时给出换算过程；"
                "4) 引用本班材料时用 [编号] 标注出处。")
            skill_id = create_skill(class_a, skill_name,
                                    "数学题的引导式讲解：公式提示 + 单位换算 + 出处引用",
                                    instructions, applicable="方程,去括号,通分,分数,换算,单位,面积,周长,公式",
                                    tools=tools_refs, source="manual")
            update_skill(skill_id, enabled=1)
            print(f"[seed] 技能「{skill_name}」已创建并启用（id={skill_id}）")
        else:
            skill_id = row["id"]
            update_skill(skill_id, tools=tools_refs, enabled=1)
            print(f"[seed] 技能「{skill_name}」已存在（id={skill_id}），已启用并更新工具白名单")

        # 4. 数学工具助手应用（幂等）
        conn = get_conn()
        try:
            row = conn.execute("SELECT id FROM ai_apps WHERE class_id = ? AND name = ?",
                               (class_a, "数学工具助手")).fetchone()
        finally:
            conn.close()
        if row is None:
            app_id = create_app_row(
                class_a, "数学工具助手",
                "绑定公式提示与单位换算 MCP 工具的数学解题应用，限定数学自习笔记为知识范围",
                template_id, [skill_id], [material_id], built_in=0, enabled=1)
            print(f"[seed] 应用「数学工具助手」已创建（id={app_id}）")
        else:
            print(f"[seed] 应用「数学工具助手」已存在（id={row['id']}），跳过")

        print("[seed] 完成。")


if __name__ == "__main__":
    main()
