# Spec: knowledge-retrieval

## Purpose

在已登录、按班级隔离的教研材料之上，为本班成员提供限定班级范围的知识库检索：正文切分为切片入库，支持关键字、向量、混合三种检索模式，每条命中可回溯至材料原文；问答接口仅在有命中切片时调用生成模型并以编号标注出处，无依据时明确返回未找到，不得编造出处。

## ADDED Requirements

### Requirement: 正文切分与索引入库

材料上传成功（第 3 课入库事务提交）后，系统 MUST 将正文按策略切分为若干切片写入切片表（`knowledge_chunks` 或等价），每条切片 MUST 记录切片文本、序号、所属材料与知识库条目、班级标识、字符区间与索引状态。系统 MUST 支持 `auto`、`custom`、`hierarchy` 三种切分策略；未指定策略时 MUST 按 `auto` 处理；原始文件与 `knowledge_entries.body_text` MUST 保持上传时的原样，预处理 MUST NOT 改写原文。

#### Scenario: 默认自动窗口切分

- **WHEN** 教师 A 上传一份合法材料且未指定切分策略
- **THEN** 系统 MUST 按自动窗口切分（最大 800 字、重叠 80 字，优先在空行、换行、句号处断开）
- **AND** 切片表中 MUST 出现该材料的若干切片记录，含文本、序号、字符区间与班级 A
- **AND** 切片记录的 `index_status` MUST 为 `ready`（嵌入失败场景除外，见「向量存储与嵌入」）

#### Scenario: 自定义分隔符切分

- **WHEN** 重建索引或上传时指定 `custom` 策略（按换行、空行或句号；最大长度 100 至 2000 字；重叠比例 0% 至 50%）
- **THEN** 系统 MUST 按指定分隔符与参数切分，无断点处按最大长度强制截断
- **AND** 超出参数取值范围的请求 MUST 被拒绝（HTTP 400）或按文档固定的默认值处理

#### Scenario: Markdown 标题分章切分

- **WHEN** 对含 Markdown 标题的材料指定 `hierarchy` 策略
- **THEN** 系统 MUST 按 `#`、`##`、`###` 层级分章，标题 MUST 保留在该章切片内
- **AND** 某章超过自动窗口长度时 MUST 再按自动窗口规则切分

#### Scenario: 预处理不改写原文

- **WHEN** 切分时启用了移除 URL/邮箱或折叠连续空白等预处理
- **THEN** 预处理 MUST 仅作用于待切分与待嵌入的文本
- **AND** `knowledge_entries.body_text` MUST 仍为上传原文
- **AND** 切片偏移量相对于预处理后文本计算，不得被当作原文件中的字符下标对外承诺

#### Scenario: 种子材料启动时补齐索引

- **WHEN** 服务启动时检测到已入库材料（含种子材料）尚无切片
- **THEN** 系统 MUST 按 `auto` 策略为其补齐切片与索引
- **AND** 嵌入服务不可用时切片 MUST 标记为 `failed` 且 MUST NOT 阻塞服务启动

### Requirement: 向量存储与嵌入

系统 MUST 将每个切片转换为一条向量写入向量库（Compose 中的 Qdrant，collection `campusclaw_chunks`，余弦度量）；向量库中 MUST 仅保存向量与若干标识，MUST NOT 保存切片正文；向量主键 MUST 与切片表主键一致。嵌入 MUST 仅在服务端调用 OpenAI 兼容的嵌入网关，密钥 MUST NOT 下发到浏览器。

#### Scenario: 两库数据形态与关联

- **WHEN** 取同一条切片对照关系库与向量库
- **THEN** 关系库中 MUST 保存切片正文、序号、班级与字符偏移
- **AND** 向量库中 MUST 保存定长浮点向量，payload 仅含 `class_id`、`material_id`、`knowledge_entry_id`、`chunk_id`、`chunk_index`
- **AND** 向量主键、切片表主键与 `payload.chunk_id` 三者 MUST 相同

#### Scenario: 嵌入失败不产生不完整数据

- **WHEN** 嵌入网关调用失败（超时、错误或维度不符）
- **THEN** 材料记录与切片记录 MUST 仍然保留
- **AND** 受影响切片 MUST 标记 `index_status = failed`
- **AND** 向量库中 MUST NOT 写入该切片的不完整向量记录

#### Scenario: 向量维度与集合一致

- **WHEN** 服务启动或首次写入向量库
- **THEN** collection 的向量维度 MUST 与所配置嵌入模型的输出维度一致
- **AND** collection 不存在时系统 MUST 按配置维度创建

### Requirement: 关键字检索

关键字模式 MUST 仅查询关系库全文索引（SQLite FTS5 trigram 或等价），MUST NOT 调用嵌入服务，MUST NOT 访问向量库；仅 `index_status = ready` 且属于会话班级的切片参与检索；结果 MUST 按全文相关度由高到低排序。

#### Scenario: 原词命中

- **WHEN** 登录用户使用直接出现在本班材料原文中的词以 `keyword` 模式检索
- **THEN** 响应 MUST 为 HTTP 200 且命中列表含该切片
- **AND** 本次请求 MUST NOT 产生问句向量（不调用嵌入网关）

#### Scenario: 改写后关键字落空但向量可命中

- **WHEN** 用户以同义改写（原词未出现在原文）分别以 `keyword` 与 `vector` 模式检索
- **THEN** `keyword` 路径 SHOULD 落空（无命中）
- **AND** `vector` 路径仍可能命中语义相近切片

### Requirement: 向量检索

向量模式 MUST 先将问句转换为向量，再在向量库中按会话班级过滤并计算余弦相似度；相似度低于 0.35 的候选 MUST 丢弃；随后 MUST 以向量主键回关系库取回切片正文，回表查询 MUST 再次以同一会话班级过滤。向量库 payload 中的标识 MUST NOT 单独作为正文来源。

#### Scenario: 语义命中与阈值过滤

- **WHEN** 用户以语义相近但措辞不同的问句以 `vector` 模式检索
- **THEN** 命中切片 MUST 按余弦相似度由高到低返回
- **AND** 相似度低于 0.35 的候选 MUST NOT 出现在结果中

#### Scenario: 回表取正文并核对班级

- **WHEN** 向量库返回命中向量主键
- **THEN** 系统 MUST 用这些主键回关系库查询切片正文
- **AND** 回表查询条件 MUST 含 `class_id = 会话班级`
- **AND** 回表未命中（含班级不符）的向量结果 MUST NOT 出现在响应中

### Requirement: 混合检索

混合模式 MUST 同时执行关键字与向量两条路径；两路 MUST 先各自按绝对分数过滤，再按名次执行 RRF（k = 60）融合为最终次序；缺席的一路 MUST NOT 贡献分数。检索接口未指定模式时 MUST 按混合模式处理。

#### Scenario: 两路均命中排序靠前

- **WHEN** 某切片同时被关键字与向量路径命中
- **THEN** 融合排序中该切片 MUST 比仅单路命中的切片更靠前

#### Scenario: 默认模式为混合

- **WHEN** 检索请求未携带 `mode` 参数
- **THEN** 系统 MUST 按 `hybrid` 模式执行检索

#### Scenario: 一路缺席不贡献分数

- **WHEN** 关键字路径落空而向量路径有命中（或相反）
- **THEN** 混合结果 MUST 仅由有命中一路的名次决定
- **AND** MUST NOT 将两路绝对分数相加或归一化求和

### Requirement: 命中结果溯源

每条命中结果 MUST 至少给出材料标题、切片序号、字符区间与一段摘录，并支持打开对应材料；摘录 MUST 取自关系库中的切片正文，而非向量库。响应与页面 MUST NOT 展示向量分量或向量库原始点数据。

#### Scenario: 命中含完整出处

- **WHEN** 检索返回非空命中列表
- **THEN** 每条命中 MUST 含材料标题、切片序号、字符区间与摘录
- **AND** 摘录 MUST 与关系库中对应 `chunk_text` 一致
- **AND** 用户 MUST 可通过材料标识打开对应材料（沿用第 3 课材料访问与隔离规则）

### Requirement: 检索侧班级隔离

检索接口的班级标识 MUST 仅取自登录会话；查询字符串、JSON 正文或请求头中携带的班级编号 MUST 在解析后丢弃；关键字与向量两条路径 MUST 均使用会话班级过滤，且回表查询 MUST 再次核对。跨班检索 MUST 对外表现为无命中，MUST NOT 以 403 或 404 暗示资料归属其他班级。

#### Scenario: 请求体中的班级编号被丢弃

- **WHEN** A 班用户在检索请求体中写入 B 班的 `class_id` 并检索一个仅出现在 B 班正文中的词
- **THEN** 响应 MUST 为 HTTP 200 且命中列表为空
- **AND** 实际过滤条件 MUST 仍为 A 班

#### Scenario: 跨班检索表现为无命中

- **WHEN** A 班用户检索一个仅存在于 B 班正文中的词（任意模式）
- **THEN** 响应 MUST 为 HTTP 200 且 `hits` 为空（或问答接口返回固定文案）
- **AND** MUST NOT 返回 403 或 404 以区分「资料属于其他班级」与「资料不存在」

#### Scenario: 单侧过滤不构成隔离

- **WHEN** 审查关键字与向量两条路径的实现
- **THEN** 关键字查询 MUST 含会话班级条件
- **AND** 向量库查询 MUST 含会话班级过滤，且回表查询 MUST 再次以同一会话班级核对

### Requirement: 问答接口与引用标注

系统 MUST 提供 `POST /api/ask` 问答接口：仅以用户最新一句发起本班混合检索并取前 4 条切片；仅当存在命中切片时才 MUST 调用生成模型撰写简短回答，回答中 MUST 以 [1]、[2] 编号指回出处，且编号顺序 MUST 与出处列表（citations）一致；无命中时 MUST 直接返回固定文案「资料中未找到相关内容」，citations 为空，且 MUST NOT 调用生成模型。

#### Scenario: 有命中时生成带标注的回答

- **WHEN** 提问在本班材料中有依据（混合检索命中至少一条切片）
- **THEN** 系统 MUST 将材料标题、切片序号、切片正文与本轮提问交给生成模型
- **AND** 回答正文中 MUST 以 [1]、[2] 标注出处，顺序与 `citations` 列表一致
- **AND** 生成模型 MUST NOT 获得向量分量或其他班级的切片

#### Scenario: 无命中时不调用生成模型

- **WHEN** 提问与本班材料无关（如天气、比分），混合检索无候选
- **THEN** 接口 MUST 返回 HTTP 200，正文为固定文案「资料中未找到相关内容」
- **AND** `citations` MUST 为空
- **AND** 本次请求 MUST NOT 调用生成模型（页面出现文字不构成模型被调用的证据）

#### Scenario: 客户端注入的 system 消息被丢弃

- **WHEN** 问答请求中携带客户端自行构造的 `system` 消息
- **THEN** 该消息 MUST 被丢弃
- **AND** system 提示 MUST 由服务端写入，仅允许模型依据编号对应的资料作答

#### Scenario: 历史对话附于其后

- **WHEN** 请求携带此前若干轮对话历史
- **THEN** 检索 MUST 仅以最新一句发起
- **AND** 历史 SHOULD 附于提问之后供生成模型参考
- **AND** 班级仍 MUST 仅从会话读取

### Requirement: 故障降级与参数校验

向量库或嵌入服务不可用时，关键字检索 MUST 仍可返回结果；向量与混合模式 MUST 返回 HTTP 503 且 MUST NOT 编造相似度分数；空查询 MUST 返回 HTTP 400。

#### Scenario: Qdrant 不可用时关键字仍可用

- **WHEN** 向量库服务停止或不可达
- **THEN** `keyword` 模式检索 MUST 仍可返回 HTTP 200 与正常结果
- **AND** `vector` 与 `hybrid` 模式 MUST 返回 HTTP 503
- **AND** 503 响应 MUST NOT 包含虚构的相似度分数或命中

#### Scenario: 空查询返回 400

- **WHEN** 检索或问答请求的问句为空串或全空白
- **THEN** 系统 MUST 返回 HTTP 400 与明确错误信息
- **AND** MUST NOT 访问向量库或生成模型

### Requirement: 索引重建

教师 MUST 可对既有材料按新策略重建索引；重建 MUST 先删除旧切片与旧向量记录，再按本次请求的策略重新切分、嵌入与写入；已入库材料 MUST NOT 自动重新切分。学生调用重建接口 MUST 被拒绝（HTTP 403）。

#### Scenario: 更换策略须显式重建

- **WHEN** 材料以 `auto` 策略入库后，教师以 `hierarchy` 策略发起重建
- **THEN** 旧切片与旧向量记录 MUST 先被删除
- **AND** 新切片 MUST 按 `hierarchy` 规则生成并重新嵌入写入
- **AND** 未发起重建时，旧切片 MUST 保持原样

#### Scenario: 学生重建被拒绝

- **WHEN** 学生 A1 调用索引重建接口
- **THEN** 系统 MUST 返回 HTTP 403
- **AND** 切片表与向量库 MUST 无变更

### Requirement: 组件暴露面与密钥

向量库服务 MUST NOT 向宿主机映射端口，MUST 仅接受应用服务在内部网络发起的调用；嵌入与对话网关密钥 MUST 仅存于服务端环境变量，MUST NOT 下发到页面或出现在 API 响应中；浏览器 MUST 仅访问本站接口。

#### Scenario: 向量库不对客户端暴露

- **WHEN** Compose 启动完成后，从宿主机直接请求向量库端口（如 `http://localhost:6333/`）
- **THEN** 连接 MUST 失败（无端口映射）
- **AND** 应用服务经内部网络访问向量库 MUST 正常

#### Scenario: 密钥不下发

- **WHEN** 检查任意页面 HTML、静态资源与 API 响应
- **THEN** MUST NOT 出现嵌入或对话网关的密钥
- **AND** MUST NOT 出现向量分量或向量库连接信息
