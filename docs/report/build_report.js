// CampusClaw 个人项目应用平台验收报告生成脚本（docx-js）
// 规范：Profile A 正式报告 + R1 封面（DM-1 Deep Cyan）+ 三节页码 + TOC
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, PageBreak, Header, Footer, PageNumber, NumberFormat,
  AlignmentType, HeadingLevel, WidthType, BorderStyle, ShadingType,
  TableOfContents, SectionType, TableLayoutType, ExternalHyperlink,
} = require("docx");
const fs = require("fs");
const sizeOf = require("image-size");

const ASSETS = __dirname + "/assets";
const OUT = __dirname + "/CampusClaw个人项目应用平台验收报告.docx";

// ── 配色（DM-1 Deep Cyan：AI/科技） ──
const P = {
  bg: "162235", accent: "37DCF2",
  cover: { titleColor: "FFFFFF", subtitleColor: "B0B8C0", metaColor: "90989F", footerColor: "687078" },
  table: { headerBg: "1B6B7A", headerText: "FFFFFF", innerLine: "C8DDE2", surface: "EDF3F5" },
  headingColor: "0A1628", body: "000000", secondary: "5A6572",
};

// ── 封面工具函数（design-system 规范） ──
function splitTitleLines(title, charsPerLine) {
  if (title.length <= charsPerLine) return [title];
  const breakAfter = new Set([..."，。、；：！？", ..."的与和及之在于为", ..."-_—–·/", ..." \t"]);
  const lines = [];
  let remaining = title;
  while (remaining.length > charsPerLine) {
    let breakAt = -1;
    for (let i = charsPerLine; i >= Math.floor(charsPerLine * 0.6); i--) {
      if (i < remaining.length && breakAfter.has(remaining[i - 1])) { breakAt = i; break; }
    }
    if (breakAt === -1) {
      const limit = Math.min(remaining.length, Math.ceil(charsPerLine * 1.3));
      for (let i = charsPerLine + 1; i < limit; i++) {
        if (breakAfter.has(remaining[i - 1])) { breakAt = i; break; }
      }
    }
    if (breakAt === -1) {
      breakAt = charsPerLine;
      const prevChar = remaining[breakAt - 1], nextChar = remaining[breakAt];
      if (prevChar && nextChar && !breakAfter.has(prevChar) && !breakAfter.has(nextChar)
          && /[\u4e00-\u9fff]/.test(prevChar) && /[\u4e00-\u9fff]/.test(nextChar)) breakAt -= 1;
    }
    lines.push(remaining.slice(0, breakAt).trim());
    remaining = remaining.slice(breakAt).trim();
  }
  if (remaining) lines.push(remaining);
  if (lines.length > 1 && lines[lines.length - 1].length <= 2) {
    const last = lines.pop();
    lines[lines.length - 1] += last;
  }
  return lines;
}

function calcTitleLayout(title, maxWidthTwips, preferredPt = 40, minPt = 24) {
  const charsPerLine = (pt) => Math.floor(maxWidthTwips / (pt * 20));
  let titlePt = preferredPt, lines;
  while (titlePt >= minPt) {
    const cpl = charsPerLine(titlePt);
    if (cpl < 2) { titlePt -= 2; continue; }
    lines = splitTitleLines(title, cpl);
    if (lines.length <= 3) break;
    titlePt -= 2;
  }
  if (!lines || lines.length > 3) {
    lines = splitTitleLines(title, charsPerLine(minPt));
    titlePt = minPt;
  }
  return { titlePt, titleLines: lines };
}

const allNoBorders = {
  top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
  left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
  insideHorizontal: { style: BorderStyle.NONE }, insideVertical: { style: BorderStyle.NONE },
};
const noBorders = {
  top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
  left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
};

// ── 实验报告封面（白底）：校徽 + 校名 + 课程实验报告 + 标题 + 信息表 ──
const NB = { style: BorderStyle.NONE };

function labInfoTable(rows) {
  return new Table({
    width: { size: 68, type: WidthType.PERCENTAGE },
    alignment: AlignmentType.CENTER,
    borders: allNoBorders,
    rows: rows.map(function (pair) {
      return new TableRow({
        cantSplit: true,
        children: [
          new TableCell({
            width: { size: 32, type: WidthType.PERCENTAGE },
            borders: { top: NB, bottom: NB, left: NB, right: NB },
            margins: { top: 100, bottom: 100, left: 120, right: 120 },
            children: [new Paragraph({
              alignment: AlignmentType.LEFT,
              spacing: { line: Math.ceil(15 * 23), lineRule: "atLeast" },
              children: [new TextRun({ text: pair[0] + "：", size: 30, bold: true, color: "000000",
                font: { eastAsia: "SimHei", ascii: "Times New Roman" } })],
            })],
          }),
          new TableCell({
            width: { size: 68, type: WidthType.PERCENTAGE },
            borders: { top: NB, left: NB, right: NB,
              bottom: { style: BorderStyle.SINGLE, size: 4, color: "000000" } },
            margins: { top: 100, bottom: 100, left: 120, right: 120 },
            children: [new Paragraph({
              alignment: AlignmentType.LEFT,
              spacing: { line: Math.ceil(15 * 23), lineRule: "atLeast" },
              children: [new TextRun({ text: pair[1], size: 30, color: "000000",
                font: { eastAsia: "SimSun", ascii: "Times New Roman" } })],
            })],
          }),
        ],
      });
    }),
  });
}

function buildLabCover(config) {
  const seal = fs.readFileSync(ASSETS + "/pku-seal.png");
  const sealSize = 200; // 200px ≈ 5.3cm 大校徽
  const children = [];

  // 顶部留白 + 校徽 + 校名
  children.push(new Paragraph({ spacing: { before: 1300 } }));
  children.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 300 },
    children: [new ImageRun({ data: seal, transformation: { width: sealSize, height: sealSize }, type: "png" })],
  }));
  children.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 260, line: Math.ceil(42 * 23), lineRule: "atLeast" },
    children: [new TextRun({ text: "北京大学", size: 84, bold: true, color: "000000",
      characterSpacing: 200,
      font: { eastAsia: "SimHei", ascii: "Times New Roman" } })],
  }));
  children.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 500, line: Math.ceil(18 * 23), lineRule: "atLeast" },
    children: [new TextRun({ text: config.docType, size: 36, color: "000000",
      font: { eastAsia: "SimSun", ascii: "Times New Roman" } })],
  }));

  // 主标题（动态字号）
  const availableWidth = 11906 - 1701 - 1417;
  const layout = calcTitleLayout(config.title, availableWidth, 28, 24);
  const titlePt = layout.titlePt, titleLines = layout.titleLines;
  for (let i = 0; i < titleLines.length; i++) {
    children.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: i < titleLines.length - 1 ? 100 : 0,
        line: Math.ceil(titlePt * 23), lineRule: "atLeast" },
      children: [new TextRun({ text: titleLines[i], size: titlePt * 2, bold: true, color: "000000",
        font: { eastAsia: "SimHei", ascii: "Times New Roman" } })],
    }));
  }

  // 信息表（下划线式）
  children.push(new Paragraph({ spacing: { before: 2100 } }));
  children.push(labInfoTable(config.infoRows));

  // 单页 16838 精确高度的白色包裹表
  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    rows: [new TableRow({
      height: { value: 16838, rule: "exact" },
      children: [new TableCell({
        shading: { type: ShadingType.CLEAR, fill: "FFFFFF" },
        borders: noBorders,
        children: children,
      })],
    })],
  })];
}

// ── 正文组件 ──
function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160, line: 312 },
    children: [new TextRun({ text, bold: true, size: 32, color: P.headingColor,
      font: { ascii: "Times New Roman", eastAsia: "SimHei" } })],
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 260, after: 120, line: 312 },
    children: [new TextRun({ text, bold: true, size: 28, color: P.headingColor,
      font: { ascii: "Times New Roman", eastAsia: "SimHei" } })],
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 100, line: 312 },
    children: [new TextRun({ text, bold: true, size: 24, color: P.headingColor,
      font: { ascii: "Times New Roman", eastAsia: "SimHei" } })],
  });
}
function body(text, opts) {
  const o = opts || {};
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { line: 312, after: o.after != null ? o.after : 60 },
    children: [new TextRun({ text, size: 24, color: P.body,
      font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
  });
}
function bodyRuns(runs) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { line: 312, after: 60 },
    children: runs,
  });
}
function rn(text, opts) {
  const o = opts || {};
  return new TextRun({ text, size: 24, bold: !!o.bold, color: o.color || P.body,
    font: { ascii: "Times New Roman", eastAsia: o.hei ? "SimHei" : "SimSun" } });
}
let figNo = 0;
function img(file, captionText, widthPx) {
  figNo += 1;
  const buf = fs.readFileSync(ASSETS + "/" + file);
  const dim = sizeOf.imageSize ? sizeOf.imageSize(buf) : sizeOf(buf);
  const w = widthPx || 520;
  const h = Math.round(w * dim.height / dim.width);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      keepNext: true,
      spacing: { before: 120, after: 40 },
      children: [new ImageRun({ data: buf, transformation: { width: w, height: h }, type: "png" })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 160 },
      children: [new TextRun({ text: "图" + figNo + "  " + captionText, size: 21, color: P.secondary,
        font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
    }),
  ];
}
let tblNo = 0;
function tblCaption(text) {
  tblNo += 1;
  return new Paragraph({
    keepNext: true, alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 60 },
    children: [new TextRun({ text: "表" + tblNo + "  " + text, size: 21, bold: true, color: P.headingColor,
      font: { ascii: "Times New Roman", eastAsia: "SimHei" } })],
  });
}
function cellPara(text, opts) {
  const o = opts || {};
  return new Paragraph({
    alignment: o.center ? AlignmentType.CENTER : AlignmentType.LEFT,
    spacing: { line: 276 },
    children: [new TextRun({ text: String(text), size: o.size || 20, bold: !!o.bold,
      color: o.color || P.body, font: { ascii: "Times New Roman", eastAsia: o.hei ? "SimHei" : "SimSun" } })],
  });
}
function tbl(headers, rows, colWidths) {
  const widths = colWidths || headers.map(() => Math.floor(100 / headers.length));
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: P.table.headerBg },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: P.table.headerBg },
      left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 1, color: P.table.innerLine },
      insideVertical: { style: BorderStyle.NONE },
    },
    rows: [
      new TableRow({
        tableHeader: true, cantSplit: true,
        children: headers.map((t, i) => new TableCell({
          children: [cellPara(t, { bold: true, center: true, color: P.table.headerText, hei: true })],
          shading: { type: ShadingType.CLEAR, fill: P.table.headerBg },
          margins: { top: 70, bottom: 70, left: 110, right: 110 },
          width: { size: widths[i], type: WidthType.PERCENTAGE },
        })),
      }),
      ...rows.map((row, ri) => new TableRow({
        cantSplit: true,
        children: row.map((t, i) => new TableCell({
          children: [cellPara(t)],
          shading: { type: ShadingType.CLEAR, fill: ri % 2 === 0 ? "FFFFFF" : P.table.surface },
          margins: { top: 60, bottom: 60, left: 110, right: 110 },
          width: { size: widths[i], type: WidthType.PERCENTAGE },
        })),
      })),
    ],
  });
}
function codeBlock(lines) {
  return lines.map((line, i) => new Paragraph({
    alignment: AlignmentType.LEFT,
    shading: { type: ShadingType.CLEAR, fill: "F5F3EE" },
    spacing: { line: 252, before: i === 0 ? 80 : 0, after: i === lines.length - 1 ? 120 : 0 },
    indent: { left: 240, right: 240 },
    children: [new TextRun({ text: line.length ? line : " ", size: 17, color: "2A2A2A",
      font: { ascii: "Courier New", eastAsia: "SimSun" } })],
  }));
}
function pageHeader() {
  return new Header({ children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: "C8DDE2", space: 4 } },
    children: [new TextRun({ text: "CampusClaw 个人项目应用平台验收报告", size: 16, color: "888888",
      font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
  })] });
}
function pageFooter() {
  return new Footer({ children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "666666",
      font: { ascii: "Times New Roman" } })],
  })] });
}

// ═══════════════ 正文内容 ═══════════════
const bodyChildren = [];

// —— 1 项目概述 ——
bodyChildren.push(h1("1  项目概述"));
bodyChildren.push(h2("1.1  项目简介"));
bodyChildren.push(bodyRuns([
  rn("CampusClaw 是北京大学《互联网软件开发技术与实践》课程的个人项目（仓库地址："),
  new ExternalHyperlink({
    children: [new TextRun({ text: "https://github.com/leaveWhite9088/CampusClaw", style: "Hyperlink", size: 24,
      font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
    link: "https://github.com/leaveWhite9088/CampusClaw",
  }),
  rn("），一个面向中小学教研场景的 AI 应用平台。教师登录后按班级上传教学材料，系统自动切分入库，本班学生用自然语言就能检索材料并定位出处；在知识库之上，平台提供应用层能力：内置多个各司其职的 AI 应用（资料问答、解题引导、作文点评等），每个应用可绑定不同的提示词模板与技能——模板规定助手的角色与回答规范，技能把「只引导不给答案」这类教学规则注入回答，也支持按课程技能文件格式直接上传；对话时系统先检索本班知识库，只把最相关的若干切片连同提问一起交给大模型，并给回答标注材料出处；平台还通过 MCP 协议接入自建的外部工具服务（公式提示、单位换算、概念速查），提问命中相应技能时服务端自动调用工具并把结果融入回答，每一次大模型调用与工具调用都有完整的日志与审计可回溯。整个系统按「班级即数据边界」设计，不同班级数据相互隔离；开发全程采用规约驱动（SDD），以 Docker Compose 一键部署。"),
]));
bodyChildren.push(h2("1.2  仓库地址与运行方式"));
bodyChildren.push(bodyRuns([
  rn("项目 Git 仓库地址：", { bold: true }),
  rn("https://github.com/leaveWhite9088/CampusClaw.git（main 分支）。本地仓库路径为 互联网软件开发技术与实践/CampusClaw，验收时的代码版本对应提交「第6课收尾」及之后各次提交。"),
]));
bodyChildren.push(body("标准启动方式为 Docker Compose。执行 cp .env.example .env 并填写 SECRET_KEY 与网关配置后，运行 docker compose up --build 即可一键启动全部五个服务：web（Nginx，对外唯一端口 8088）、app（gunicorn + Flask，不映射宿主端口）、qdrant（向量库，仅内部网络）、mcp-server（自建 MCP 工具服务，仅内部网络）。应用提供 GET /health 健康检查。首次启动自动建表并写入种子数据；执行 docker compose exec app python scripts/seed_demo.py 可一键准备演示数据（登记并连接 MCP 服务器、创建数学解题引导技能与数学工具助手应用）。"));
bodyChildren.push(body("预置账号：教师 teacher_a / teach123（班级 A），学生 student_a1 / stu123（班级 A），student_b1 / stu123（班级 B）。嵌入与对话网关在本机以 scripts/dev_stub_gateway.py（OpenAI 兼容的抽取式 stub）扮演，密钥只放在服务端 .env，不入库、不进镜像、不进前端。"));
bodyChildren.push(...img("01-login.png", "系统登录页（http://localhost:8088/login）"));
bodyChildren.push(...img("02-materials-teacher.png", "登录后首页：本班材料与知识库检索"));
bodyChildren.push(h2("1.3  一次提问的总体链路"));
bodyChildren.push(body("无论从哪个应用发起提问，服务端都按同一条链路编排：取会话所属应用的绑定（提示词模板、技能、材料范围），按适用条件选中技能，先做本班混合检索（SQLite FTS5 关键字 + Qdrant 向量，RRF 融合取前 4 条切片），再按技能工具白名单确定性调用 MCP 工具（若有绑定），最后把「渲染后的模板 + 选中技能的完整指令 + 编号资料切片 + 工具返回数据块 + 用户提问」组装成对话网关请求，以 SSE 流式返回回答与出处。每一次调用对话网关的完整请求参数与返回内容都写入 LLM 调用日志，作为本报告第 3 章逐项验证的取证依据。"));
bodyChildren.push(h2("1.4  功能要求对照"));
bodyChildren.push(body("作业要求的五项功能与系统实现的对应关系如表 1 所示，全部功能均已实现并在 Docker Compose 环境跑通。", { after: 40 }));
bodyChildren.push(tblCaption("作业功能要求与系统实现对照"));
bodyChildren.push(tbl(
  ["作业要求", "系统实现", "主要入口"],
  [
    ["内置多个 AI 应用", "每班预置 3 个内置应用（资料问答、解题引导、作文点评），教师可自建应用并绑定模板/技能/材料范围", "/apps、/api/apps"],
    ["支持提示词模板", "prompt_templates 表 + 每班 3 个内置模板，支持 {{skills}}/{{knowledge}} 占位符，应用绑定模板渲染为 system 消息", "/settings 模板页签、/api/templates"],
    ["支持知识库检索", "沿用 SQLite FTS5 + Qdrant 混合检索（RRF），应用可限定材料子集；回答带 [编号] 出处标注", "/materials、/api/search"],
    ["内置 Skill 并支持上传", "每班预置 3 条内置技能；支持课程技能文件格式（.md/.json）上传，解析适用条件与工具白名单并做保存前校验", "/settings 技能页签、/api/skills/upload"],
    ["外部工具及 MCP 接入", "同仓自建 mcp-server（JSON-RPC 2.0，3 个工具）；教师登记/连接/断开；技能以 工具名@服务器名 绑定；命中即带令牌调用并写审计", "/settings MCP 页签、mcp-server/"],
  ],
  [22, 50, 28]
));

// —— 2 功能实现 ——
bodyChildren.push(h1("2  功能实现详解"));

bodyChildren.push(h2("2.1  功能一：内置多个 AI 应用"));
bodyChildren.push(h3("2.1.1  设计与数据模型"));
bodyChildren.push(body("「AI 应用」是平台的核心组织层：一个应用把一次问答所需的三类配置打包在一起——一个提示词模板（决定助手的角色与回答规范）、若干技能（决定注入哪些指令、触发哪些工具）、一个材料范围（限定知识库检索边界，空表示本班全部材料）。数据层新增 ai_apps 表，字段包括 class_id、name、description、template_id、skill_ids（JSON 数组）、material_ids（JSON 数组）、built_in 与 enabled。绑定校验在服务端完成：模板、技能、材料必须属于本班，跨班绑定返回 400。"));
bodyChildren.push(body("每班预置 3 个 built_in 应用作为开箱即用的演示：资料问答助手（默认教研模板，纯知识库问答）、解题引导助手（解题引导模板 + 解题引导技能）、作文点评助手（作文点评模板 + 作文点评技能）。内置应用不可删除，只能停用；教师自建的应用可删除，删除后历史会话自动回退为无应用会话。"));
bodyChildren.push(tblCaption("本班预置的 AI 应用（班级 A 演示数据）"));
bodyChildren.push(tbl(
  ["应用", "提示词模板", "绑定技能", "知识库范围"],
  [
    ["资料问答助手（内置）", "默认教研模板", "（无）", "本班全部材料"],
    ["解题引导助手（内置）", "解题引导模板", "解题引导", "本班全部材料"],
    ["作文点评助手（内置）", "作文点评模板", "作文点评", "本班全部材料"],
    ["数学工具助手（教师自建）", "解题引导模板", "数学解题引导（含 2 个 MCP 工具）", "指定材料 1 份（数学自习笔记）"],
  ],
  [26, 22, 30, 22]
));
bodyChildren.push(h3("2.1.2  接口与页面"));
bodyChildren.push(body("应用相关接口共 6 个：GET/POST /api/apps、PUT/DELETE /api/apps/{id}（教师写、全班读）、POST /api/apps/{id}/conversations（在应用下新建会话，学生会话记录 app_id 归属）。页面 /apps 以卡片展示本班全部应用，教师可见「新建应用」表单（模板下拉、技能多选、材料范围多选）；学生只见进入入口，无任何管理表单。应用内对话页 /apps/{id} 复用第 5 课的 SSE 流式交互，并在顶部展示该应用的绑定信息，回答带 [编号] 出处标注。"));
bodyChildren.push(...img("03-apps-teacher.png", "AI 应用页（教师视角：4 个应用 + 新建应用表单）", 500));
bodyChildren.push(...img("20-apps-student.png", "AI 应用页（学生视角：只读，无管理入口）", 500));
bodyChildren.push(h3("2.1.3  使用步骤演示"));
bodyChildren.push(body("第一步，以教师 teacher_a 登录，进入「AI 应用」页，可见 3 个内置应用与 1 个自建的数学工具助手；第二步，点击「资料问答助手」卡片上的「进入应用」（该应用绑定默认教研模板、不绑定技能、知识库为本班全部材料），在应用内点击「＋ 新对话」；第三步，输入问题「单位换算 分数 方程 都是什么」并发送，回答以 SSE 逐段返回并带出处标注（如图 5，命中最相关的数学自习笔记 2 个切片并标注出处）。学生会话的 app_id 持久化保存，再次进入应用可继续历史会话；带 MCP 工具调用的应用会话演示见 2.5.3 节。"));
bodyChildren.push(...img("12-app-qa-wholeclass.png", "在「资料问答助手」应用内提问（本班全部材料范围，回答带出处）", 500));

bodyChildren.push(h2("2.2  功能二：支持提示词模板"));
bodyChildren.push(h3("2.2.1  设计与渲染规则"));
bodyChildren.push(body("数据层新增 prompt_templates 表（class_id、name、content、built_in）。每班预置 3 个内置模板：默认教研模板、解题引导模板、作文点评模板。模板正文支持两个占位符：{{skills}} 表示技能指令块的注入位置，{{knowledge}} 表示编号资料块的注入位置；渲染时先替换占位符，模板未出现的占位块按「技能、资料」顺序追加在末尾，最后拼接固定的引用边界句（仅依据资料作答、[编号] 标注出处）。渲染结果作为对话网关请求的 system 消息——因此模板内容一定会随请求传给 LLM，这一点在第 3 章验证一中以调用日志为证。"));
bodyChildren.push(h3("2.2.2  接口与页面"));
bodyChildren.push(body("接口为 GET/POST /api/templates 与 PUT/DELETE /api/templates/{id}：登录可读，仅教师可写；内置模板可编辑、不可删除；删除自定义模板后，引用它的应用自动回退为班级提示词。/settings 的「提示词模板」页签提供列表、编辑与新建（如图 6），「班级提示词」页签保留第 5 课的班级级提示词，用于无应用归属的旧会话（如图 7）。"));
bodyChildren.push(...img("06-settings-templates.png", "提示词模板页签：3 个内置模板 + 新建表单（占位符说明）", 500));
bodyChildren.push(...img("05-settings-prompt.png", "班级提示词页签（无应用旧会话使用）", 460));

bodyChildren.push(h2("2.3  功能三：支持知识库检索"));
bodyChildren.push(body("知识库检索沿用第 4 课已验收的能力并做了应用层扩展：教师上传 .txt/.md 材料后自动切分（auto/custom/hierarchy 三种策略）并建立 SQLite FTS5 关键字索引与 Qdrant 向量索引；检索支持 keyword、vector、hybrid 三种模式，混合检索用 RRF（k=60）融合两路结果，向量余弦阈值 0.35；不足 3 字符的短词自动降级为 LIKE 子串匹配。所有检索强制带会话班级条件，回表取正文时再次核对班级与 ready 状态。"));
bodyChildren.push(body("本次新增的应用层扩展是「材料范围过滤」：应用若绑定了材料子集，会话检索结果先按子集过滤再取前 4 条，且回表统计知识库总量时也只统计子集范围——数学工具助手绑定了「数学自习笔记」一份材料，因此它的日志显示知识库总量为 2 个切片（1156 字），而全库应用的日志显示 6 个切片（1465 字）。检索本身不变，边界由服务端收窄。"));
bodyChildren.push(body("需要注意的一点是：系统每次请求只把检索命中的前 4 条切片传给 LLM，而不是把知识库全部内容传过去；具体的数据对比与日志证据见第 3 章验证二。"));

bodyChildren.push(h2("2.4  功能四：内置 Skill 技能与上传技能"));
bodyChildren.push(h3("2.4.1  技能模型与内置技能"));
bodyChildren.push(body("技能（Skill）是一段可被选中的完整指令，配合适用条件与工具白名单工作。skills 表扩展了 applicable（适用条件关键词，逗号分隔，留空表示总是生效）、tools（工具白名单，支持内置的 knowledge_search 与 MCP 引用 工具名@服务器名）、source（built_in / uploaded / manual）三个字段。每班预置 3 条内置技能：解题引导（只引导不给答案）、概念讲解（先定义再举例，适用「概念、定义、是什么」等关键词）、作文点评（按选材/结构/语言三条点评，适用「作文、写作」等关键词）。"));
bodyChildren.push(h3("2.4.2  技能上传：课程技能文件格式"));
bodyChildren.push(body("POST /api/skills/upload 接受 multipart 文件（.md/.txt/.json）。.md 文件按课程技能文件格式解析：头部逐行为「键：值」（支持全角冒号），键包括名称（必填）、简介、适用条件、工具、启用（是/否，默认否）；空行之后全部作为指令正文。.json 格式接受 name、description、instructions、applicable、tools、enabled 字段。解析完成后逐条校验工具引用：格式必须为 knowledge_search 或符合规则的 工具名@服务器名（工具名小写字母开头，仅小写字母、数字、下划线；服务器名另允许连字符），且服务器必须本班已登记、已连接、工具在发现缓存内——任一不成立整份拒绝并返回可读原因。上传成功后技能以 source=uploaded 入库，列表页即时可见（如图 9 中的「古诗鉴赏引导」）。"));
bodyChildren.push(tblCaption("班级 A 的技能清单（演示数据）"));
bodyChildren.push(tbl(
  ["技能", "来源", "适用条件", "工具白名单", "状态"],
  [
    ["解题引导", "built_in", "（总是生效）", "knowledge_search", "已启用"],
    ["概念讲解", "built_in", "概念、定义、什么意思、是什么、解释", "knowledge_search", "停用"],
    ["作文点评", "built_in", "作文、点评、写作、范文、修改", "knowledge_search", "停用"],
    ["数学解题引导", "manual", "方程、去括号、通分、分数、换算、单位、面积、周长、公式", "knowledge_search, formula_hint@campus-tools, unit_convert@campus-tools", "已启用"],
    ["古诗鉴赏引导", "uploaded", "古诗、唐诗、宋词、赏析", "knowledge_search", "已启用"],
  ],
  [18, 12, 30, 28, 12]
));
bodyChildren.push(...img("07-settings-skills.png", "技能页签：技能清单（适用条件/工具白名单/来源）+ 新建 + 上传表单", 500));
bodyChildren.push(...img("19-skill-uploaded.png", "上传「古诗鉴赏引导」技能文件后出现在列表（source=uploaded）", 500));

bodyChildren.push(h2("2.5  功能五：外部工具及 MCP 接入"));
bodyChildren.push(h3("2.5.1  自建 MCP 服务器（mcp-server/）"));
bodyChildren.push(body("仓库同仓新增 mcp-server/ 目录，用 Python 标准库实现了一个 MCP 工具服务：POST /mcp 提供 JSON-RPC 2.0 报文（initialize 握手、tools/list 发现、tools/call 调用），GET /health 提供健康检查；Bearer 令牌从环境变量 MCP_AUTH_TOKEN 读取，令牌缺失或错误返回 401，非法请求返回可读的 JSON-RPC 错误（-32700/-32601/-32602）。服务由 docker-compose.yml 与主应用一并构建启动，不映射宿主端口，仅 Compose 内部网络可达，主应用通过 http://mcp-server:8090 访问。暴露 3 个工具，见表 4。"));
bodyChildren.push(tblCaption("campus-tools MCP 服务暴露的工具"));
bodyChildren.push(tbl(
  ["工具", "功能", "参数"],
  [
    ["formula_hint", "按关键词（去括号/通分/方程/面积/勾股等）给出公式与步骤提示，不给最终数值答案", "query（提问原文）"],
    ["unit_convert", "长度/质量/时间单位换算，可从自然语言问句解析数值与单位（如「把 5 米换成厘米」）", "query（提问原文，可附 value/from/to）"],
    ["concept_lookup", "小学数学概念速查（分数/方程/面积/周长/质数等），返回简明定义", "query（概念或提问原文）"],
  ],
  [20, 56, 24]
));
bodyChildren.push(h3("2.5.2  主机侧：登记、连接与发现"));
bodyChildren.push(body("主应用新增三张表：mcp_servers（本班登记的服务器，令牌只存服务端）、mcp_tools（连接时发现的工具缓存，每次连接覆盖写入）、mcp_tool_calls（调用审计，只增不改）。教师通过 /settings 的「MCP 服务器」页签登记服务器（名称、Base URL、Bearer 令牌，令牌输入框为密码型，提交后清空不回显），再点「连接并发现」：服务端先 initialize 握手、再 tools/list 取回工具清单，覆盖写入缓存并标记已连接；任一步失败返回 502、状态置回未连接且不写缓存。「断开」清空缓存；「删除」级联清空缓存并保留审计证据。接口响应只含 has_auth 布尔，任何响应都不回传令牌原文。8 个管理接口全部挂在「登录 + 仅教师」之后，学生访问返回 403，他班服务器按编号访问与不存在一致返回 404。"));
bodyChildren.push(...img("08-settings-mcp.png", "MCP 服务器页签：campus-tools 已连接（3 个工具）+ 调用审计", 500));
bodyChildren.push(...img("15-swagger-mcp.png", "Swagger 页的 MCP 接口分组（8 个管理接口可试调）", 500));
bodyChildren.push(h3("2.5.3  技能绑定与对话中的调用"));
bodyChildren.push(body("技能的「工具」栏写入 MCP 引用（如 formula_hint@campus-tools）即完成绑定；保存（新建、修改、上传）时做四道校验：引用格式、服务器存在、已连接、工具在发现清单内，任一不过整份拒绝。学生提问命中带 MCP 工具的技能时，服务端按技能白名单逐个调用（跳过 knowledge_search）：调用参数只含提问原文 query，不由模型生成；返回先过安全校验（命中「忽略前述」等指令式句式或超 1200 字整条丢弃），再以 [工具 xxx@yyy 返回的数据] 前缀作为数据拼进用户消息，不进入 system 消息。SSE 流先推 meta 事件（含 tool_calls 清单与状态）再推回答片段，前端在回答开始前就显示「用了哪个工具」。对话页的绿色工具标签（图 12）即来自 meta 事件。"));
bodyChildren.push(...img("04-app-chat-tools.png", "数学工具助手内提问：formula_hint 与 unit_convert 两个 MCP 工具被调用（ok），回答带出处", 500));
bodyChildren.push(h3("2.5.4  断开后的行为"));
bodyChildren.push(body("断开不是静默失效。服务器断开后，工具缓存清空，下一次提问命中该技能时调用被记为 denied（响应的 tool_calls 与审计表都可见），回答主路径照常进行——工具是增益而非主路径。图 13、图 16 与图 17 展示了完整过程：断开后服务器显示未连接、工具 0 个（图 13）；提问时两个工具标签均显示 denied、回答照常返回（图 16）；审计表新增两条「服务器未连接」的 denied 记录（图 17）；重新连接后恢复正常。"));
bodyChildren.push(...img("16-mcp-disconnected.png", "断开 campus-tools：状态未连接、工具缓存清空", 460));

// —— 3 验证内容 ——
bodyChildren.push(h1("3  验证内容：五项逐项验证"));
bodyChildren.push(body("本章针对作业要求的五个验证项逐项给出结论、验证方法与证据。所有证据来自运行中的系统：调用日志（/settings 的「LLM 调用日志」页签，数据表 llm_call_logs）完整记录了每次发给对话网关的请求 JSON 与返回内容，是各项验证的直接取证依据。", { after: 100 }));

bodyChildren.push(h2("3.1  验证一：每次对话传给 LLM 的具体参数与返回内容；提示词模板是否一并传递"));
bodyChildren.push(bodyRuns([
  rn("结论：", { bold: true }),
  rn("每次对话传给 LLM 接口的是一个 OpenAI 兼容的 /chat/completions 请求体，包含 model、messages（system 一条 + 历史若干 + user 一条）与 stream 字段；返回内容为 choices[0].message.content。提示词模板内容会一并传递——应用绑定的模板渲染后作为 system 消息的第一部分发给 LLM。"),
]));
bodyChildren.push(body("验证方法：教师在「数学工具助手」应用内新建会话并提问「去括号法则是什么」，随后打开 /settings 的「LLM 调用日志」页签查看本次调用的详情。日志完整保存了发出的请求 JSON 与返回文本（图 14 上半部分为请求参数，下半部分为返回内容）。"));
bodyChildren.push(...img("10-log-detail-full.png", "调用日志详情：发给 LLM 的完整请求参数与返回内容（含模板、技能、资料、工具数据块）", 520));
bodyChildren.push(body("本次请求的实际参数摘要如下（摘自调用日志 #2，request_json 字段原文节选）："));
bodyChildren.push(...codeBlock([
  '{',
  '  "model": "stub-chat",',
  '  "messages": [',
  '    { "role": "system", "content": "你是本班的解题引导老师，语气温和有耐心。',
  '        要求：一次只指出下一步该检查什么，不代替学生完成整道题。   ← 应用绑定的「解题引导模板」正文',
  '        技能「数学解题引导」：你是数学解题引导助手。规则：1) 先判断题目考查的知识点…… ← 选中技能的完整指令',
  '        [1] 材料《A 班·数学自习笔记》第 0 节：……                            ← 检索命中的编号资料',
  '    { "role": "user", "content": "去括号法则是什么" },',
  '  ],',
  '  "stream": false',
  '}',
  '返回：choices[0].message.content = 「括号前面是减号时，去掉括号和括号前的减号，括号里每一项都要变号。[1]」',
]));
bodyChildren.push(body("日志同时记录了模板名（解题引导模板）、注入技能（数学解题引导）与知识库统计，与页面配置完全一致。对无应用归属的旧会话，模板位置由班级提示词充当，模板名记录为「班级提示词」，行为向后兼容（日志 #3）。"));

bodyChildren.push(h2("3.2  验证二：绑定知识库后，是否把知识库全部内容传给 LLM"));
bodyChildren.push(bodyRuns([
  rn("结论：", { bold: true }),
  rn("不会。每次请求只把混合检索命中的前 4 条切片（编号资料）传给 LLM，知识库其余内容不传递。调用日志为每次请求记录了四个数：知识库切片总量与字符总量（kb_total_chunks / kb_total_chars），以及实际传入的切片数与字符数（kb_passed_chunks / kb_passed_chars），对比一目了然。"),
]));
bodyChildren.push(body("验证方法：班级 A 的知识库共有 6 个 ready 切片、1465 字（含 4 份材料）。分别在三种范围下提问并查看调用日志，得到表 5 的对比数据。", { after: 40 }));
bodyChildren.push(tblCaption("同一班级三种知识库范围下「全库内容 vs 实际传入」的日志数据"));
bodyChildren.push(tbl(
  ["提问场景", "知识库总量", "实际传入", "说明"],
  [
    ["旧会话（班级提示词），问「生字词 课文导读」", "6 切片 / 1465 字", "1 切片 / 19 字", "仅命中语文讲义 1 个切片"],
    ["资料问答助手（本班全部材料），问「单位换算 分数 方程」", "6 切片 / 1465 字", "2 切片 / 1156 字", "命中数学笔记 2 个切片，其余 4 个不传"],
    ["数学工具助手（限定数学笔记），问「去括号法则」", "2 切片 / 1156 字", "1 切片 / 754 字", "应用材料子集进一步收窄边界"],
  ],
  [40, 20, 20, 20]
));
bodyChildren.push(...img("13-log-detail-wholeclass.png", "全库应用（资料问答助手）的日志详情：传入 2/6 切片、1156/1465 字", 520));
bodyChildren.push(body("日志列表页的每一行都直接展示「传入/总量」，例如「2/6 切片 · 1156/1465 字」（图 19）。即使检索满额命中 4 条，也只是 6 条中的 4 条；切片内容始终按相关度筛选，而非全量粘贴。"));

bodyChildren.push(h2("3.3  验证三：绑定技能后，请求中是否包含该技能的全部内容"));
bodyChildren.push(bodyRuns([
  rn("结论：", { bold: true }),
  rn("是。被选中技能的 instructions（完整指令正文）会一字不少地注入 system 消息。日志的 skill_names 字段记录本轮注入了哪些技能，request_json 的 system 消息里可以逐字找到技能全文。"),
]));
bodyChildren.push(body("对照方法分两步。第一步，在 /settings 的技能页签查看「数学解题引导」的指令全文（共 4 条规则：先判断知识点、只指出下一步、单位换算给过程、引用材料标出处）；第二步，打开同一次提问的调用日志详情，system 消息中「技能「数学解题引导」：」之后的内容与技能页全文逐字一致（见 3.1 节代码摘录第三行）。日志详情页头部同时展示「注入技能：数学解题引导」，与该次请求实际注入的技能一一对应。"));
bodyChildren.push(body("补充两点边界行为：其一，技能按适用条件筛选——「作文点评」技能的适用条件是「作文、点评、写作」等关键词，提问不含这些词时该技能不会被选中、其指令也不注入（单元测试 test_applicable_keyword_gates_skill 覆盖了正反两个方向）；其二，应用只绑定已启用的技能，停用的技能不参与编排。"));

bodyChildren.push(h2("3.4  验证四：执行具体技能 Skill 时的执行逻辑"));
bodyChildren.push(body("技能的执行分「内容型」与「工具型」两类，统一走「先检索、再调工具、后生成」的确定性编排，调用时机与参数由服务端代码决定，不由模型临场决定。完整步骤如下。", { after: 40 }));
bodyChildren.push(tblCaption("一次会话提问的技能执行流程"));
bodyChildren.push(tbl(
  ["步骤", "动作", "说明"],
  [
    ["1 会话归属", "取会话所属应用的绑定", "模板、技能清单、材料范围；旧会话回退为班级提示词 + 全部启用技能"],
    ["2 选技能", "按适用条件筛选", "applicable 为空则总是选中；有关键词则提问命中任一关键词才选中"],
    ["3 检索", "本班（或应用子集）混合检索取前 4 条", "向量路径不可用时关键字兜底；无命中直接返回固定文案，不调模型也不调工具"],
    ["4 调工具", "按选中技能的工具白名单逐个调用", "跳过 knowledge_search；参数只含提问原文；未连接记 denied 并写审计，服务器不存在记响应 denied 但无审计行"],
    ["5 安全校验", "工具返回过句式与长度校验", "命中「忽略前述」等指令式句式或超 1200 字，整条丢弃"],
    ["6 组装", "渲染模板 + 技能全文注入 system；工具返回作数据拼进 user 消息", "外部内容一律不进 system，位置边界防注入"],
    ["7 生成", "调用对话网关，写一条 LLM 调用日志", "完整请求与返回留痕（见 3.1 节）"],
    ["8 流式返回", "SSE：meta（tool_calls）→ delta 若干 → citations → done", "前端先显示工具标签再流式渲染回答；工具失败不中断主路径"],
  ],
  [16, 34, 50]
));
bodyChildren.push(body("内容型技能（如解题引导、作文点评）的执行效果就是第 6 步：指令全文进入 system，模型按指令约束回答方式（解题引导只给思路不给答案）。工具型技能（如数学解题引导）在第 4 步多了真实的外部调用：图 12 中提问「去括号法则是什么」触发了 formula_hint 与 unit_convert 两个 MCP 工具调用（均 ok），formula_hint 返回的去括号法则提示作为数据出现在 user 消息里（见 3.5 节摘录），模型最终回答引用了资料 [1]。断开服务器后同一技能再提问，两个工具标签变为 denied、回答照常返回（图 16），审计表新增 denied 记录（图 17）——调用失败是局部失败，不影响检索与流式回答主路径。"));
bodyChildren.push(...img("17-chat-tool-denied.png", "断开 MCP 后同一技能提问：tool_calls 记为 denied，回答主路径不受影响", 500));
bodyChildren.push(...img("18-mcp-audit-denied.png", "审计表：新增两条 denied 记录（服务器未连接），历史 ok 记录保留", 500));

bodyChildren.push(h2("3.5  验证五：集成 MCP 工具后，每次请求传给 LLM 的具体参数"));
bodyChildren.push(bodyRuns([
  rn("结论：", { bold: true }),
  rn("MCP 集成不改变请求结构（仍是 model + messages + stream），改变的是 user 消息的内容：通过安全校验的工具返回以 [工具 工具名@服务器名 返回的数据] 为前缀拼进用户消息；system 消息中不出现任何工具返回。调用清单（引用与状态）另行记录在日志的 tool_calls 字段与 SSE 的 meta 事件中。"),
]));
bodyChildren.push(body("以下是 3.1 节同一次请求（日志 #2）user 消息的完整原文，可以清楚看到提问原文与两个工具返回数据块的拼接方式："));
bodyChildren.push(...codeBlock([
  '"role": "user",',
  '"content": "去括号法则是什么"',
  '',
  '[工具 formula_hint@campus-tools 返回的数据]',
  '根据你的问题，给一条相关公式/法则提示（不给最终答案）：去括号时：括号前的系数要乘到',
  '括号内每一项，符号不要漏变；括号前是减号时，去掉括号后里面每一项都要变号。',
  '',
  '[工具 unit_convert@campus-tools 返回的数据]',
  '单位换算工具：请提供数值与两个单位（如「把 5 米换成厘米」）。支持长度（km/m/dm/cm/mm）、',
  '质量（t/kg/g）、时间（h/min/s）。',
]));
bodyChildren.push(body("工具调用的另一侧报文同样留了证据。在 app 容器内直连 mcp-server 抓取的原始 JSON-RPC 交互如下（完整文件见仓库 docs/report/evidence/mcp-jsonrpc.txt）：主机侧每次 tools/call 的 params 只含工具名与 arguments.query（提问原文），响应的 result.content 为文本数组。"));
bodyChildren.push(...codeBlock([
  '请求: {"jsonrpc":"2.0","id":1,"method":"tools/call",',
  '       "params":{"name":"formula_hint","arguments":{"query":"去括号这一步我不会"}}}',
  '响应(HTTP 200): {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text",',
  '  "text":"根据你的问题，给一条相关公式/法则提示（不给最终答案）：去括号时：括号前的系数要乘到括号内每一项……"}],"isError":false}}',
  '',
  '请求(自然语言取参): {"name":"unit_convert","arguments":{"query":"把 5 米换成厘米"}}',
  '响应(HTTP 200): {"result":{"content":[{"type":"text","text":"换算过程：5.0 米 = 5.0 × 1 ÷ 0.01 = 500 厘米。"}],"isError":false}}',
  '',
  '错误令牌: HTTP 401 {"error":"unauthorized"}    未知方法: {"error":{"code":-32601,"message":"未知方法：no/such/method"}}',
]));
bodyChildren.push(body("综合两侧报文可以完整回答「传给 LLM 的具体参数」：system = 渲染后的模板 + 技能全文 + 编号资料 + 引用边界句；user = 提问原文 + 工具返回数据块；model 与 stream 由服务端配置给定。工具令牌不出服务端，接口响应只回 has_auth 布尔，全程未出现在任何发往 LLM 的内容里。"));

// —— 4 测试 ——
bodyChildren.push(h1("4  测试与质量保障"));
bodyChildren.push(h2("4.1  测试体系"));
bodyChildren.push(body("项目维护了三层测试，全部可在全新环境一键执行。本次验收前全量重跑，结果见表 7。", { after: 40 }));
bodyChildren.push(tblCaption("测试执行结果汇总（2026-10-22）"));
bodyChildren.push(tbl(
  ["测试层", "内容", "结果"],
  [
    ["tests/test_lesson4.py", "切分、三种检索、溯源、班级隔离、降级（第 4 课回归）", "37 项全部通过"],
    ["tests/test_lesson5.py", "提示词/技能权限与注入、会话归属、SSE 事件序列、OpenAPI（第 5 课回归）", "11 项全部通过"],
    ["tests/test_lesson6.py", "AI 应用/模板 CRUD 与绑定校验、应用会话编排（模板与技能注入、材料子集）、技能上传解析、LLM 调用日志字段", "11 项全部通过"],
    ["tests/test_mcp.py", "MCP 协议（握手/发现/调用/401/-32601）、登记与令牌边界、连接缓存覆盖、绑定四道校验、对话调用/审计/denied、注入拦截", "13 项全部通过"],
    ["apitest/run_all.py", "13 个接口用例（登录/检索/提示词/技能/上传/应用/模板/会话消息/日志/MCP 登记/连接/审计），检查项含返回内容与数据库一致性核对", "13/13 用例通过"],
  ],
  [24, 56, 20]
));
bodyChildren.push(h2("4.2  API 文档与试调"));
bodyChildren.push(body("全部 33 个 API 路径书写在 openapi.json（OpenAPI 3.0），/swagger 页面离线加载本地 vendor 的 Swagger UI，可直接配置 Bearer 令牌试调，包括 MCP 的登记、连接、查工具、审计等主要接口（图 18）。", { after: 40 }));
bodyChildren.push(...img("14-swagger.png", "Swagger 接口文档页（离线可用，含本次新增的全部接口）", 500));
bodyChildren.push(h2("4.3  运维可观测性"));
bodyChildren.push(body("除 LLM 调用日志列表外（图 19），MCP 调用审计（mcp_tool_calls，只增不改）按班隔离供教师回放每次工具调用（见前文图 10 与图 17）；docker compose ps 与 /health 提供服务健康状态；数据经 ./data、./uploads 与 qdrant_storage 卷持久化，重启不丢。", { after: 40 }));
bodyChildren.push(...img("09-settings-logs.png", "LLM 调用日志列表：每行展示模板、模型、知识库传入/总量与状态", 500));

// —— 5 总结 ——
bodyChildren.push(h1("5  总结"));
bodyChildren.push(body("本项目在既有登录认证、班级隔离、材料入库与混合检索的基础上，按规约驱动开发完成了个人项目应用平台的全部五项功能：以 ai_apps 为核心的多个内置 AI 应用、支持占位符渲染的提示词模板、可限定材料范围的知识库检索、内置与可上传的技能体系，以及带鉴权、审计与信任边界的 MCP 外部工具接入。作业要求的五项验证内容均通过运行中的系统逐项取证：调用日志证明模板与技能全文随请求传递、知识库只传检索命中的切片、MCP 工具返回作为数据拼进用户消息；审计与 SSE meta 事件证明技能的执行是服务端确定性编排，断开即失效、失败不中断主路径。"));
bodyChildren.push(body("后续可改进的方向包括：真实嵌入与对话网关接入后的语义检索效果调优、技能路由从关键词匹配升级为向量路由、以及输出侧的外发意图检查（当前防线为「数据只进用户消息位置 + 句式校验 + 模型不持有工具开关」三层中的前两层，输出侧检查尚待补强）。"));

// ═══════════════ 组装文档 ═══════════════
const doc = new Document({
  creator: "CampusClaw",
  title: "CampusClaw 个人项目应用平台验收报告",
  styles: {
    default: {
      document: {
        run: { font: { ascii: "Times New Roman", eastAsia: "SimSun" }, size: 24, color: "000000" },
        paragraph: { spacing: { line: 312 } },
      },
      heading1: {
        run: { font: { ascii: "Times New Roman", eastAsia: "SimHei" }, size: 32, bold: true, color: P.headingColor },
        paragraph: { spacing: { before: 360, after: 160, line: 312 }, outlineLevel: 0 },
      },
      heading2: {
        run: { font: { ascii: "Times New Roman", eastAsia: "SimHei" }, size: 28, bold: true, color: P.headingColor },
        paragraph: { spacing: { before: 260, after: 120, line: 312 }, outlineLevel: 1 },
      },
      heading3: {
        run: { font: { ascii: "Times New Roman", eastAsia: "SimHei" }, size: 24, bold: true, color: P.headingColor },
        paragraph: { spacing: { before: 200, after: 100, line: 312 }, outlineLevel: 2 },
      },
    },
  },
  sections: [
    { // 封面
      properties: {
        page: { size: { width: 11906, height: 16838 }, margin: { top: 0, bottom: 0, left: 0, right: 0 } },
      },
      children: buildLabCover({
        docType: "《互联网软件开发技术与实践》课程实验报告",
        title: "CampusClaw 个人项目应用平台验收报告",
        infoRows: [
          ["课程名称", "互联网软件开发技术与实践"],
          ["项目名称", "CampusClaw 教研智能体平台"],
          ["姓名", "唐梓鑫"],
          ["学号", "2601210752"],
          ["日期", "2026 年 10 月 22 日"],
        ],
      }),
    },
    { // 前置：目录（罗马页码）
      properties: {
        type: SectionType.NEXT_PAGE,
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, bottom: 1440, left: 1701, right: 1417 },
          pageNumbers: { start: 1, formatType: NumberFormat.UPPER_ROMAN },
        },
      },
      headers: { default: pageHeader() },
      footers: { default: pageFooter() },
      children: [
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 480, after: 360 },
          children: [new TextRun({ text: "目  录", bold: true, size: 32,
            font: { eastAsia: "SimHei", ascii: "Times New Roman" } })],
        }),
        new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" }),
        new Paragraph({
          spacing: { before: 200 },
          children: [new TextRun({
            text: "注：本目录由域代码生成。编辑后请在目录上点击右键并选择「更新域」以刷新页码。",
            italics: true, size: 18, color: "888888",
            font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
        }),
        // 目录与正文分属不同节（NEXT_PAGE），此处不加 PageBreak 以免产生空白页
      ],
    },
    { // 正文（阿拉伯页码，从 1 起）
      properties: {
        type: SectionType.NEXT_PAGE,
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, bottom: 1440, left: 1701, right: 1417 },
          pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL },
        },
      },
      headers: { default: pageHeader() },
      footers: { default: pageFooter() },
      children: bodyChildren,
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log("written:", OUT, buf.length, "bytes,", figNo, "figures,", tblNo, "tables");
});
