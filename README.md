# EchoClass

> AI-powered 1v1 Q&A coach for pre-service teachers.
> 师范生 1v1 答疑陪练系统 —— 让未来的教师在走上讲台前，先反复练习"被学生追问"。

参赛项目：**华东师范大学开发者大赛 2026 · 大语言模型创新应用开发赛道**
赛事官网：<https://developer.ecnu.edu.cn/competition2026/>

---

## ✨ 项目简介

### 痛点

师范生在象牙塔里积累了大量教育学理论，但**真正走上讲台前缺乏与"会问真实问题的学生"反复对练的机会**：

- **同伴扮演的温室效应**：师范生互相扮"小学生"时背景太接近，提不出真实的儿童式困惑
- **答疑场景比试讲更稀缺**：多数人**没经历过一次完整的"被学生连续追问"**，而那才是教学功底真正的试金石
- **缺乏脚手架训练**：识别学生迷思 → 命中错误前提 → 用合适粒度逐步纠偏，这套能力只能在大量真实对话中习得

### 使用流程

```
[1] 上传教案（PDF / Markdown / TXT）→ 自动抽取学科 / 学段 / 教学目标 / 重点 / 难点
[2] 选学段 + 挑虚拟学生人设（6 学段 × 3 学生 = 18 种典型组合）
[3] 学生根据教案"主动提问" → 多个候选问题供老师选
[4] 老师选一个问题进入 1v1 答疑对话（流式渲染）
    · 学生按人设说话，带犹豫 / 口头禅 / 孩子腔
    · 含错误前提的问题不轻易"懂"，要被讲到点子上才行
[5] 学生末尾输出 [懂了] 标记 → self_resolved 触发该题结束
[6] 进下一题 / 切学生 / 结束 session
```

### 关键设计点

- **双层人设建模（学段共性 × 个体差异）**
  6 档学段特征库（皮亚杰认知阶段 + 思维方式 + 语言风格）做硬性认知边界，避免 LLM "小学一年级开口讲微积分"的超模问题；18 个学生人设叠加性格、口头禅、迷思倾向。

- **学科迷思概念库驱动错误生成**
  21 份学科 × 学段迷思 JSON（覆盖小初高数/理/化/生/语文/英语/史地政），由 `match_misconceptions(subject, stage_id, key_points, ...)` 动态匹配最多 3 条注入 prompt——薄弱学生的错误不是随机的，而是**真实教学研究里发现的典型迷思**。

- **学生提问的"宽生成 + self-check + 多样性筛选"管线**
  `StudentAgent.generate_questions` 二阶段：第一阶段宽生成 N + overshoot 个候选；第二阶段让 agent 自评 (人设贴合度 + 教育价值 + 教案相关性)，剔除 keep=false / score<60；最后按类别多样性贪心 + self_score 排序取 top N。

- **流式 `[懂了]` HOLDBACK 缓冲**
  学生末尾的 `[懂了]` 标记不能流式推到前端，否则会破坏体验。`stream_in_dialog` 在推送增量时永远保留尾部 16 字符不发出，流结束后剥离 `[懂了]` 再补一个 `delta` 事件 + 最终 `final` 事件——前端只看到学生自然说完话。

- **维果茨基脚手架的强制练习**
  prompt 显式约束：含 `stuck_misconception` 类别的问题，**老师不真正讲到错误前提之前学生不会"懂"**。逼迫师范生练习"识别迷思 → 命中靶心 → 分级解释"。

- **教育学知识库（EduKB）锚点驱动可解释人设**
  8 张教育学理论卡片（Bandura 自我效能 / Vygotsky ZPD / Posner 概念改变 / Piaget 认知阶段 / Pekrun 学业情绪 / Deci-Ryan 自我决定 / Weiner 归因 / Chi 迷思分类）持久化在 SQLite + Chroma 双存储。每个 persona 通过 `theory_anchors` 锚定到具体 trait 上，让"为什么这个学生会这样反应"在生成时可追溯到学术依据。post-merge POC 验证：4 锚点注入使 anxious persona 的 `self_deprecation_rate` 从 0% → 40%（N=10 稳定）。

## 📌 当前进度

> 阶段划分见 [`docs/roles.md`](./docs/roles.md)。详细任务分解：A / B / C 各角色 M1 / M2 / M3 表。

### 后端（A-Agent）— M1 / M2 已收尾，M3 启动

- ✅ FastAPI 脚手架 + CORS + `/health` + 统一 `ApiResponse` 响应包络
- ✅ `LLMClient`：OpenAI 兼容（ChatECNU ecnu-max 默认）+ tenacity 重试 + token 日志 + stream 包装
- ✅ `StudentAgent` 三件套：
  - `generate_questions` — 宽生成 + self-check + 多样性筛选
  - `respond_in_dialog` — 多轮 1v1 对话
  - `stream_in_dialog` — 流式推送 + `[懂了]` HOLDBACK 缓冲
- ✅ 教案 RAG：`parser`（pymupdf4llm）→ `extractor`（LLM 抽取 LessonMeta）→ `indexer`（500 token 切片 + Chroma 向量化）
- ✅ 学科迷思 RAG：`match_misconceptions(subject, stage_id, key_points, ...)`
- ✅ 6 学段 ask/chat few-shot 范例选择器（`rag.qa_examples`）
- ✅ `QASession` 骨架（services 层）：问题队列 + 1v1 对话状态机
- ✅ REST API：`/api/lessons/upload|{id}` · `/api/stages[/{id}]` · `/api/personas[/{name_or_id}]`
- ✅ **EduKB 第一期** ([#84](https://github.com/echoclass-team/EchoClass/issues/84)) — 教育学知识库持久化与进化骨架：
  - `kb/models.py` 5 张表 SQLAlchemy ORM（理论 / trait / 锚点 / 观察事件 / 候选迷思）
  - `kb/database.py` + alembic 迁移（SQLite + StaticPool）
  - `kb/poc_loader.py` 双路径加载（DB 优先 / JSON fallback）
  - `kb/evolution.py` 进化引擎：观察事件 + 候选迷思状态机 + 锚点增删 + 全程审计
  - `kb/retrieval.py` Chroma 向量检索（trait 粒度，metadata 过滤）
  - `scripts/seed_edu_kb.py` JSON → DB 种子导入器（幂等 + orphan 清理 + dry-run）
  - `scripts/build_theory_index.py` Chroma 索引构建器
- ✅ 197 单元 / 集成测试（含 EduKB +43，mock LLM 不走网络）
- ✅ WebSocket 1v1 流式答疑端到端（与 B 共建完成）
- ✅ SQLite 持久化（与 B 共建完成）
- 🚧 答疑后反馈 Agent（迷思命中率 / 脚手架质量打分，M3）
- 🚧 EduKB 第二期：LLM-as-Judge 接入 / evolution 接 session 钩子 / Chroma 中文 embedding 切换

### 前端（B-Full）— M1 已收尾，M2 进行中

- ✅ Next.js 14（App Router）+ TypeScript + TailwindCSS 脚手架
- ✅ Setup 三段式：`/setup/stage`（学段）→ `/setup/config`（教案 + 学生）→ `/classroom/demo`（演示骨架）
- ✅ 教案上传（调用 `/api/lessons/upload`）+ 本地教案库 localStorage 暂存
- ✅ `apiFetch` 统一 client（`ApiResponse` envelope 解析 + `ApiError` 类）
- ✅ 类型定义严格对齐后端 schema（Stage / Persona / LessonMeta / LessonRecord）
- 🚧 1v1 答疑 UI（提问列表 → 选题 → 流式对话 + `[懂了]` 视觉处理）
- 🚧 WebSocket client + 后端 endpoint 端到端
- 🚧 `/api/sessions` REST + SQLite 持久化
- 📋 答疑反馈页可视化（迷思命中高亮 / 轮次拆解 / 改进建议卡片，M3）

### 产品 / 评测（C-Prod）— M1 / M2 已收尾，M3 启动

- ✅ 立项书 v1（1v1 答疑陪练版，[`docs/proposal.md`](./docs/proposal.md)）
- ✅ 6 学段 stage_profile JSON
- ✅ 18 学生人设 JSON（已于 v1.1 移除 4 个 Director 时代死字段，详见 [`docs/persona_design.md`](./docs/persona_design.md)）
- ✅ 21 份学科 × 学段迷思概念库 JSON
- ✅ 6 份跨学段样例教案（小低 / 小中 / 小高 / 初低 / 初高 / 高中，PDF + Markdown + meta）
- ✅ 6 学段 ask/chat few-shot 范例集合（与 A 协作落入 `rag/qa_examples`）
- ✅ **EduKB 第一期内容** ([#85](https://github.com/echoclass-team/EchoClass/issues/85))：
  - **8 张教育学理论卡片** (`data/edu_theories/`)：Bandura · Vygotsky · Posner · Piaget · Pekrun · Deci-Ryan · Weiner · Chi
  - **6 个学段代表 persona** 接入 `theory_anchors`（共 22 条锚点，schema v1.2 cross-ref 校验）
  - 设计文档 [`docs/edu_kb_design.md`](./docs/edu_kb_design.md)（动机 / 理论选型 / 知识库架构 / Rubric 引用映射）
  - 关系图 [`docs/edu_kb_theory_map.md`](./docs/edu_kb_theory_map.md)（理论 ↔ persona / misconception 三向锚点 mermaid）
  - POC 评估 [`docs/edu_kb_post_merge_eval.md`](./docs/edu_kb_post_merge_eval.md)（N=5/10 锚点效应稳定）
- 🚧 答疑专项评估 Rubric 初版 + 评估 prompt v1（基于 EduKB 理论引用）
- 🚧 用户测试方案（招募标准 + 测试任务卡 + 反馈表）
- 📋 真人师范生测试 × 5+ 轮 + Demo 视频 + 答辩 PPT（M3）

## 🏗️ 技术栈

| 层 | 技术 | Owner |
|---|---|---|
| **前端** | Next.js 14（App Router）· TypeScript · TailwindCSS · shadcn/ui · Zustand · TanStack Query · Recharts · lucide-react | **B** |
| **API / 协议** | FastAPI · WebSocket（JSON Lines）· REST · uv 依赖管理 · 统一 `ApiResponse` 包络 | **B** |
| **Agent** | StudentAgent（generate_questions + respond_in_dialog + stream_in_dialog）· QASession 编排 · 宽生成 + self-check 二阶段 | **A** |
| **LLM 接入** | OpenAI 兼容（ChatECNU ecnu-max 默认；可切 DeepSeek / Qwen）· openai 客户端 · tenacity 重试 · token 使用日志 | **A** |
| **RAG** | Chroma 向量库 · pymupdf4llm（PDF → Markdown）· Jinja2 Prompt 模板 · 500 token 切片 · 迷思动态匹配 · few-shot 选择器 | **A** |
| **教育学建模** | 6 档学段认知特征库（皮亚杰 / 维果茨基）· 18 学生人设 JSON · 21 份学科迷思概念库 | A / C |
| **持久化** | SQLite + SQLAlchemy 2.x · alembic 迁移 · `kb_*` 表（理论卡 / 锚点 / 观察事件 / 候选迷思）+ 业务表（会话 / 对话 / 问题记录） | A / B |
| **教育学知识库（EduKB）** | 8 张理论卡片 → SQLite + Chroma 双存储 · `theory_anchors` persona 锚点 · 进化引擎骨架（observation + 候选迷思状态机 + 全程审计） | A / C |
| **评估** | 答疑专项 Rubric → 第二期 LLM-as-Judge（基于 EduKB 理论引用） | A / C |
| **测试** | pytest + pytest-asyncio（后端 mock LLM）· Vitest + Playwright（前端，可选） | A / B |

## 📁 目录结构

```
EchoClass/
├── backend/                     # Python 3.11+ · FastAPI
│   ├── agents/                  # StudentAgent（generate_questions / respond_in_dialog / stream_in_dialog）
│   ├── services/                # QASession（1v1 答疑会话编排）
│   ├── rag/                     # 教案与迷思 RAG
│   │   ├── parser.py            # PDF / MD / TXT → 纯文本（pymupdf4llm）
│   │   ├── extractor.py         # LLM 抽取 subject / grade / topic / objectives / key_points / difficult_points
│   │   ├── indexer.py           # 500 token 切片 + Chroma 向量化
│   │   ├── misconceptions.py    # 学科迷思库加载 + match_misconceptions
│   │   └── qa_examples.py       # 6 学段 ask/chat few-shot 范例选择器
│   ├── llm/                     # LLMClient 封装（chat / stream + 重试 + token 日志）
│   ├── kb/                      # 🆕 教育学知识库（EduKB 第一期）
│   │   ├── models.py            # 5 张表 SQLAlchemy ORM（kb_theory / trait / anchor / observation / candidate）
│   │   ├── database.py          # Engine / Session 工厂 + SQLite 优化
│   │   ├── poc_loader.py        # 理论卡片加载（DB 优先 / JSON fallback / 强制三模式）
│   │   ├── evolution.py         # 进化引擎：观察事件 + 候选迷思状态机 + 锚点增删 + 审计
│   │   ├── retrieval.py         # Chroma 向量检索（trait 粒度 + metadata 过滤）
│   │   └── README.md            # KB 模块用法
│   ├── alembic/                 # 🆕 数据库迁移（initial_kb_schema baseline）
│   ├── prompts/                 # Jinja2 Prompt 模板
│   │   ├── student_ask.j2       # 学生根据教案生成问题（含同学段 few-shot）
│   │   ├── student_chat.j2     # 学生 1v1 多轮对话（含 [懂了] 自我宣称解决 + theory_anchors 注入）
│   │   ├── student_check.j2    # 二阶段 self-check 评分
│   │   └── extractor.j2        # 教案元数据抽取
│   ├── api/                     # REST 路由 + WebSocket endpoint（M2）
│   │   ├── lessons.py           # POST /api/lessons/upload · GET /api/lessons/{id}
│   │   ├── stages.py            # GET /api/stages · GET /api/stages/{id}
│   │   ├── personas.py          # GET /api/personas · GET /api/personas/{name_or_id}
│   │   └── response.py          # ApiResponse 包络辅助
│   ├── schemas/                 # Pydantic 模型
│   │   ├── stage.py             # StageProfile（学段认知特征）
│   │   ├── student.py           # Persona / ClassroomContext（v1.1 收紧到 14 字段）
│   │   ├── lesson.py            # LessonMeta / LessonRecord
│   │   ├── question.py          # StudentQuestion（含 self_score / category / difficulty / linked_*）
│   │   ├── dialog.py            # DialogSession / DialogMessage / DialogReplyResult / StudentStreamEvent
│   │   ├── misconception.py     # Misconception
│   │   └── api.py               # 统一 ApiResponse 包络
│   ├── db/                      # 业务持久化（会话 / 对话 / 问题记录）
│   ├── scripts/                 # 冒烟测试与 CLI demo
│   │   ├── try_qa_session.py    # 1v1 答疑陪练交互 demo（真实 LLM）
│   │   ├── try_lesson_rag.py    # 教案 RAG 完整管线
│   │   ├── validate_personas.py # 18 个 persona JSON 完整性校验（含 theory_anchors cross-ref）
│   │   ├── seed_edu_kb.py       # 🆕 JSON → SQLite 种子导入器（create / reset / dry-run / upsert）
│   │   ├── build_theory_index.py# 🆕 Chroma 理论卡片索引构建器
│   │   └── poc_compare.py       # 🆕 EduKB 锚点效应 baseline vs anchored 对比
│   ├── tests/                   # pytest 单元 / 集成测试
│   ├── main.py                  # FastAPI 入口
│   └── pyproject.toml
├── frontend/                    # TypeScript · Next.js 14
│   ├── src/app/                 # App Router：首页 / setup / classroom / lessons / sessions
│   ├── src/components/setup/    # Setup 流程（学段 / 教案 / 人设）
│   ├── src/lib/api/             # apiFetch 客户端（ApiResponse envelope + ApiError）
│   ├── src/lib/setup-storage.ts # 本地教案库 localStorage 持久化
│   └── src/types/               # Stage / Persona / Lesson 类型（严格对齐后端）
├── data/
│   ├── stage_profiles/          # 6 档学段认知特征 JSON
│   ├── personas/                # 18 学生人设 JSON（schema v1.2，6 个含 theory_anchors）
│   ├── misconceptions/          # 21 份学科 × 学段迷思概念库
│   ├── lesson_samples/          # 6 份跨学段样例教案（PDF + MD + meta）
│   ├── edu_theories/            # 🆕 8 张教育学理论卡片（EduKB 第一期）
│   ├── echoclass.db             # 🆕 SQLite 持久化（gitignored，由 seed_edu_kb 生成）
│   └── chroma_data/             # 🆕 Chroma 向量库（gitignored）
├── docs/
│   ├── roles.md                 # 三人分工细则（M1/M2/M3 阶段计划）
│   ├── api_contract.md          # API 合约
│   ├── persona_design.md        # 学生人设设计文档（v1.1 适配 1v1）
│   ├── proposal.md              # 立项书 v1（1v1 答疑陪练）
│   ├── edu_kb_design.md         # 🆕 EduKB 设计文档（动机 / 选型 / 架构 / Rubric 引用）
│   ├── edu_kb_theory_map.md     # 🆕 理论 ↔ persona / misconception 锚点关系图
│   ├── edu_kb_poc_results.md    # 🆕 EduKB POC 对比结果（N=10）
│   └── edu_kb_post_merge_eval.md # 🆕 第一期 post-merge 端到端评估
├── .github/                     # PR / Issue 模板
├── CONTRIBUTING.md              # 协作规范
└── README.md
```

## 👥 团队分工

> 完整分工细则见 **[`docs/roles.md`](./docs/roles.md)**，以下为速览。

| 角色 | 代号 | 负责人 | 核心职责 | 代码领地 |
|---|---|---|---|---|
| **Agent 工程师** | `A-Agent` | **[@Nekooo915](https://github.com/Nekooo915)** | LLM 客户端封装、StudentAgent 三件套、RAG 管线、QASession 编排、流式 `StudentStreamEvent` 生产 | `backend/{agents,services,rag,llm,prompts,schemas}` |
| **全栈工程师** | `B-Full` | **[@Traumere7](https://github.com/Traumere7)** | 前端 1v1 答疑 UI 与反馈页、**WebSocket 端到端**（消费 A 的 `stream_in_dialog`）、REST 路由、SQLite 会话持久化、视觉与落地页 | `frontend/`、`backend/{api,db}` |
| **产品 / 评测** | `C-Prod` | **[@IST00](https://github.com/IST00)** | 立项书与答辩材料、学生人设设计与维护、学科迷思概念库、答疑专项评估 Rubric、用户测试、Demo 视频 | `data/`、`docs/`、`backend/prompts/` |

### A ↔ B 内部契约

- A 暴露 `StudentAgent.stream_in_dialog` 这个 async generator，产出 `StudentStreamEvent`（`delta` × N + `final`）
- B 在 WS endpoint `async for` 这个 generator → 序列化为 JSON Lines 推给前端
- 事件 schema 在 `backend/schemas/dialog.py` + `backend/schemas/events.py`（M2 待补 WS 包装）；任何变更须两人连署

### M1 / M2 / M3 一览

| 阶段 | A-Agent | B-Full | C-Prod |
|---|---|---|---|
| **M1** ✅ | StudentAgent 三件套 + RAG + 迷思 + few-shot + QASession 骨架 | FastAPI 脚手架 + REST + 前端 Setup 三段式 + apiFetch | 立项书 v1 + 6 学段 + 18 人设 + 21 迷思库 + 6 样例教案 + few-shot 范例 |
| **M2** ✅ | QASession 端到端打磨 + 流式 `[懂了]` 稳定性 + WS 事件契约 + **EduKB 第一期持久化与进化骨架** | WebSocket 端到端 + 1v1 答疑 UI + SQLite 持久化 + shadcn/ui 升级 | 答疑专项 Rubric + 评估 prompt + 用户测试方案 + **EduKB 8 卡片 + 6 锚点 persona + 设计文档** |
| **M3** � | 答疑后反馈 Agent + **EduKB 第二期（LLM-as-Judge / evolution session 钩子 / Chroma 中文 embedding）** + 性能调优 + （stretch）ASR/TTS | 反馈页可视化 + 落地页 + 视觉打磨 | 真人测试 × 5+ 轮 + 答辩 PPT + Demo 视频 + EduKB Rubric 引用映射上线 |

### 🚀 下一阶段（M3）核心目标

- **A-Agent** — EduKB 第二期：
  - LLM-as-Judge 接入（基于 EduKB 理论引用 + Rubric 维度自动评分师范生答疑）
  - `evolution.py` 接 session 钩子（运行时自动 `record_observation` + 候选迷思自动检测）
  - Chroma 切多语种 embedding（解决当前 MiniLM 中文召回弱问题）
  - 答疑后反馈 Agent：迷思命中率 / 脚手架质量打分，输出可读改进建议

- **B-Full** — 反馈与落地：
  - 反馈页可视化（迷思命中高亮 / 轮次拆解 / 改进建议卡片 / 理论引用气泡）
  - 落地页 + 视觉打磨（参赛答辩用）

- **C-Prod** — 验证与材料：
  - 真人师范生测试 × 5+ 轮（招募 + 任务卡 + 反馈表）
  - 答辩 PPT + Demo 视频
  - EduKB Rubric 引用映射正式版（5 维度 × 主辅理论矩阵实装）

## 🚦 协作 & 开发

- **协作规范**：[`CONTRIBUTING.md`](./CONTRIBUTING.md)
- **分工细则**：[`docs/roles.md`](./docs/roles.md)
- **任务看板**：<https://github.com/orgs/echoclass-team/projects/1>
- **Issue 列表**：<https://github.com/echoclass-team/EchoClass/issues>
- **API 合约**：[`docs/api_contract.md`](./docs/api_contract.md)
- **人设设计**：[`docs/persona_design.md`](./docs/persona_design.md)
- **立项书**：[`docs/proposal.md`](./docs/proposal.md)

### 新成员 Onboarding

1. 阅读本 README + [`CONTRIBUTING.md`](./CONTRIBUTING.md) + [`docs/roles.md`](./docs/roles.md) + [`docs/proposal.md`](./docs/proposal.md)
2. 认领自己的 Role（A / B / C）
3. 从 Issue 列表里挑一个本里程碑（`m2`）的任务，分配给自己
4. 按 [`CONTRIBUTING.md`](./CONTRIBUTING.md) 流程开分支、写代码、开 PR

```bash
gh issue develop <N> --repo echoclass-team/EchoClass --checkout
```

### 本地启动后端

详见 [`backend/README.md`](./backend/README.md)。快速开始：

```bash
cd backend
uv sync --extra dev                       # 安装依赖（先装 uv：curl -LsSf https://astral.sh/uv/install.sh | sh）
cp .env.example .env                      # 填入 OPENAI_API_KEY 等
uv run uvicorn main:app --reload --port 8000
# 验证：curl http://localhost:8000/health        →  {"status":"ok"}
# 查看学段：curl http://localhost:8000/api/stages
# 查看人设：curl http://localhost:8000/api/personas
uv run pytest                             # 运行全部测试
```

### 本地启动前端

```bash
cd frontend
npm install
npm run dev                               # http://localhost:3000
```

前端默认连后端 `http://localhost:8000`，覆盖请在 `frontend/.env.local`：

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

页面入口：

- `/` — 首页 + 本地教案库预览
- `/setup/stage` — 选学段
- `/setup/config` — 选教案 + 选学生
- `/classroom/demo` — 课堂演示骨架（M2 替换为 1v1 答疑 UI）

### 常用命令

```bash
# 1v1 答疑陪练交互 demo（真实 LLM）
uv run python scripts/try_qa_session.py
uv run python scripts/try_qa_session.py --lesson math_h2_derivative --students 2 --questions 2

# 教案 RAG 完整管线（解析 → 抽取 → 索引）
uv run python scripts/try_lesson_rag.py

# 18 个 persona JSON 完整性校验（不调 LLM）
uv run python scripts/validate_personas.py

# EduKB 一键起库：建表 + 导入 8 卡片 + 22 锚点
uv run alembic upgrade head
uv run python scripts/seed_edu_kb.py --reset

# EduKB Chroma 理论卡片向量索引
uv run python scripts/build_theory_index.py
uv run python scripts/build_theory_index.py --sanity-query "焦虑学生"

# EduKB 锚点效应对比（需真实 LLM）
uv run python scripts/poc_compare.py --n 5     # baseline vs anchored各跑 5 轮
```

## 📜 License

MIT
