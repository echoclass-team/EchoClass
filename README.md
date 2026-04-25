# EchoClass

> AI-powered Q&A coaching for pre-service teachers.
> 师范生 1v1 答疑陪练系统 —— 让未来的教师在走上讲台前先被 AI 学生"问倒"几百次。

参赛项目：**华东师范大学开发者大赛 2026 · 大语言模型创新应用开发赛道**
赛事官网：<https://developer.ecnu.edu.cn/competition2026/>

> ⚠️ **产品方向已转型**：原"完整课堂回合制模拟"经过完整探索后，于 2026-04-25 主动转向
> "1v1 答疑陪练"。详细决策与新架构见 [`docs/PIVOT.md`](./docs/PIVOT.md)。
> 旧 `DirectorAgent` / `ClassroomGraph` 已归档至 `backend/legacy/` 作为设计回顾。

---

## ✨ 项目简介

### 背景

师范生最高频、最痛苦的备课动作不是"讲课"，而是**被学生问倒**：

- **真人试讲难**：组织一节真实课堂代价高，一次只能留下 40 分钟录音和模糊印象
- **反馈滞后**：导师点评稀缺，错了就是真的失败，没有重来一次的机会
- **学生反应千差万别**：薄弱生、优等生、走神生、爱跑题生——真实课堂永远只能遇到一种组合
- **教案到实战的鸿沟**：写教案时计划详尽，一到课堂上就发现"这个概念孩子根本听不懂"

### 使用流程

EchoClass 是一个基于教育学双层建模的 1v1 答疑陪练系统：

1. **上传教案** — 支持 PDF / Markdown / TXT，系统自动解析并抽取学科、学段、教学目标、知识点、难点
2. **选择学段与学生** — 从小学低年级到高中共 6 档学段、每档 3 种典型学生（共 18 个虚拟学生人设）
3. **学生主动提问** — AI 学生 Agent 根据自己的人设 × 教案内容**主动构思**会问老师的问题（含 5 类 category × 3 档难度，关联具体教学重点与学科迷思）
4. **微信式 1v1 答疑** — 师范生从问题队列里选学生进入 1v1 对话；多个学生可切换
5. **退出总结** — 统计已解答 / 放弃数、覆盖的教学重点、破除的学科迷思

### 关键设计点

- **双层建模（学段共性 × 个体差异）**：先用 6 档学段特征库（基于皮亚杰认知发展阶段、维果茨基最近发展区、埃里克森心理社会理论、教育部《中小学心理健康教育指导纲要》）约束学生的认知上限，再叠加个体人设（性格、口头禅、学业水平、迷思倾向），避免 LLM 常见的"小学一年级开口讲微积分"失真。

- **学生主动提问 vs 被动应答**：颠倒了"老师讲、学生答"的传统模拟范式，更接近真实辅导场景，也最贴合师范生备课时的高频痛点（"如果学生这样问我能答上来吗？"）。

- **学科迷思概念库驱动的提问与对话**：学生的错误前提不是随机的，而是从学科常见迷思概念库里挑选（如小学分数加法常把分子分母分别相加）。``stuck_misconception`` 类问题的对话只有当老师**真正击中错误前提**时学生才会承认"懂了"。

- **二阶段 self-check 提升问题质量**：generate_questions 内部跑两次 LLM——先宽生成 N+overshoot 个候选，再让 agent 自评（人设贴合度 + 教育价值 + 教案相关性），最后做类别多样性筛选取 top N。

- **同学段 few-shot 注入**：6 个学段各维护 2 个 ask 范例 + 2 个 chat 范例（[`data/qa_examples/`](./data/qa_examples/)），渲染 prompt 时按当前 persona 自动挑选注入，显著提升口语化与人设贴合度。

- **教案 RAG 检索**：上传的教案会被解析、切片、向量化并索引，问题与对话围绕教案实际内容展开。

## 📌 当前进度

截至本次更新（M1 闭环完成，M2 准备启动）：

**后端（A-Agent）**

基础设施（沿用）：
- ✅ FastAPI 脚手架 + CORS + `/health`
- ✅ LLMClient 封装（ChatECNU ecnu-max，OpenAI 兼容接口 + tenacity 重试 + token 日志）
- ✅ 18 个学生人设 JSON + 完整 18 字段 Persona 模型
- ✅ 6 档学段认知特征库（StageProfile，基于皮亚杰 / 维果茨基 / 埃里克森）
- ✅ 教案 RAG 管线：parser（pymupdf4llm）→ extractor（LLM 结构化抽取）→ indexer（Chroma 切片向量化）
- ✅ 学科迷思概念库（``rag.misconceptions``）+ 按学段 / 重点匹配
- ✅ REST API：`/api/lessons/upload|{id}` · `/api/lessons/{id}/recommended-personas` · `/api/stages[/{id}]` · `/api/personas[/{name_or_id}]`
- ✅ 6 份跨学段样例教案（小低 / 小中 / 小高 / 初低 / 初高 / 高中，Markdown + PDF + 解析预期）

1v1 答疑陪练（M1 完成）：
- ✅ ``StudentAgent.generate_questions(lesson_meta)`` — 宽生成 + 二阶段 self-check + 类别多样性筛选
- ✅ ``StudentAgent.respond_in_dialog(question, ...)`` — 1v1 多轮对话，含 `[懂了]` 自我宣称解决
- ✅ ``QASession`` orchestrator — 替代旧 ClassroomGraph，管理学生提问队列与对话状态机
- ✅ 6 学段 few-shot 范例集合（`data/qa_examples/`）+ 按 persona 自动挑选注入
- ✅ 新 prompt 模板：`student_ask.j2` / `student_chat.j2` / `student_check.j2`
- ✅ CLI demo：`scripts/try_qa_session.py`（含 `/resolve` `/abandon` `/switch` `/done`）
- ✅ **136 条单元 & 集成测试全绿**

下一阶段：
- ⏳ M2 — 流式 chunk + WebSocket endpoint v2（让 B 端微信式 UI 可接入）
- ⏳ M3 — 评估闭环（结合学生自我宣称 + 师范生手动 override）
- ⏳ M4 — 评估 Agent 自动判分（v2，时间允许时做）

旧方向（已归档至 `backend/legacy/`，不再 CI）：
- ⛔ DirectorAgent 多学生调度
- ⛔ LangGraph 课堂回合制状态机
- ⛔ 旧 `AgentEvent` 协议（DirectorEvent / BoardUpdateEvent 等）

**前端（B-Full）**

- ✅ Next.js 14 + TypeScript + TailwindCSS 脚手架
- ✅ Setup 流程雏形：学段选择（`/setup/stage`）→ 教案 + 学生配置（`/setup/config`）→ 课堂演示页
- ✅ 教案上传（调用 `/api/lessons/upload`） + 本地教案库暂存（localStorage）
- ✅ `apiFetch` 统一 API client（ApiError 类 + envelope 解析 + `code !== 0` 业务错误抛异常）
- ✅ 类型定义严格对齐后端 schema（Stage / Persona / LessonMeta / LessonRecord）
- ⏳ Setup 流程调整：教案 → 默认学段与默认学生 → 开始模拟（对接推荐学生接口）
- ⏳ 虚拟课堂 UI + WebSocket client（第二阶段）
- ⏳ 诊断报告页面 + 数据可视化（第三阶段）
- ⏳ shadcn/ui 组件化（Toast / Skeleton / Alert 替换手写）

**产品 / 评测（C-Prod）**

- ✅ 立项书 v4
- ✅ 学生人设设计文档
- ✅ 6 份跨学段样例教案
- ⏳ 学科迷思概念库
- ⏳ 评估 Rubric + Flanders 互动分析表

## 🏗️ 技术栈

| 层 | 技术 | Owner |
|---|---|---|
| **前端** | Next.js 14（App Router）· TypeScript · TailwindCSS · shadcn/ui · Zustand · TanStack Query · Recharts | **B** |
| **API / 协议** | FastAPI · WebSocket（JSON Lines）· REST · CORS · uv | **B** |
| **Agent 编排** | 1v1 dialog session 管理（普通 async service 类）· few-shot + self-check 二阶段质量增强 | **A** |
| **LLM 接入** | ChatECNU ecnu-max（OpenAI 兼容接口）· openai 客户端 · tenacity 重试 · token 使用日志 | **A** |
| **RAG** | Chroma 向量库 · pymupdf4llm（PDF → Markdown）· Jinja2 Prompt 模板 · 500 token 切片 | **A** |
| **教育学建模** | 6 档学段认知特征库 · 18 个学生人设 JSON · 学科迷思概念库 | A / C |
| **持久化** | SQLite（会话 / 消息） | **B** |
| **评估** | Flanders 互动分析 · 自定义 Rubric · LLM-as-a-Judge | A / C |
| **测试** | pytest + pytest-asyncio（后端）· Vitest + Playwright（前端，可选） | A / B |
| **ASR / TTS**（可选增强） | 阿里云 Paraformer / CosyVoice | A |

## 📁 目录结构

```
EchoClass/
├── backend/                     # Python 3.11+ · FastAPI
│   ├── agents/
│   │   └── student.py           # StudentAgent — generate_questions / respond_in_dialog
│   ├── services/
│   │   └── qa_session.py        # QASession orchestrator（1v1 答疑会话编排）
│   ├── rag/
│   │   ├── parser.py            # PDF / MD / TXT → 纯文本
│   │   ├── extractor.py         # LLM 抽取 subject/grade/topic/objectives/key_points/difficult_points
│   │   ├── indexer.py           # 500 token 切片 + Chroma 向量化
│   │   ├── misconceptions.py    # 学科迷思概念库加载与匹配
│   │   └── qa_examples.py       # few-shot 范例集合加载（按学段 + persona）
│   ├── llm/                     # LLMClient 封装（chat / stream + 重试 + 日志）
│   ├── api/                     # REST 路由（B 端）
│   │   ├── lessons.py           # POST /api/lessons/upload · GET /api/lessons/{id}[/recommended-personas]
│   │   ├── stages.py            # GET /api/stages[/{id}]
│   │   └── personas.py          # GET /api/personas[/{name_or_id}]
│   ├── schemas/
│   │   ├── stage.py             # StageProfile（学段认知特征）
│   │   ├── student.py           # Persona / ClassroomContext
│   │   ├── lesson.py            # LessonMeta / LessonRecord / RecommendedPersonasData
│   │   ├── question.py          # StudentQuestion（含 self_score / category / difficulty / linked_*）
│   │   ├── dialog.py            # DialogSession / DialogMessage / DialogReplyResult
│   │   └── misconception.py     # Misconception
│   ├── prompts/                 # Jinja2 Prompt 模板
│   │   ├── student_ask.j2       # 学生根据教案生成问题（含同学段 few-shot）
│   │   ├── student_chat.j2      # 学生 1v1 多轮对话（含 [懂了] 标记）
│   │   ├── student_check.j2     # 二阶段 self-check 评分
│   │   └── extractor.j2         # 教案元数据抽取
│   ├── db/                      # 会话持久化（SQLite，规划中，B 端）
│   ├── legacy/                  # 旧课堂回合制架构归档（CI 不收，仅供回顾）
│   ├── scripts/                 # 冒烟测试脚本
│   └── tests/                   # pytest 单元与集成测试（136 passed）
├── frontend/                    # TypeScript · Next.js 14 + TailwindCSS（B 端）
├── data/
│   ├── stage_profiles/          # 6 档学段认知特征 JSON
│   ├── personas/                # 18 个学生人设 JSON
│   ├── qa_examples/             # 6 学段 few-shot 范例集合
│   ├── lesson_samples/          # 样例教案（PDF + Markdown + 解析预期）
│   ├── misconceptions/          # 学科迷思概念库
│   └── eval_rubrics/            # 评估评分标准（规划中）
├── docs/
│   ├── roles.md                 # 三人分工细则
│   ├── api_contract.md          # API 合约
│   ├── persona_design.md        # 人设设计文档
│   ├── proposal.md              # 立项书
│   └── PIVOT.md                 # 产品方向转型 RFC（M1-M4 路线图）
├── .github/                     # PR / Issue 模板
├── CONTRIBUTING.md              # 协作规范
└── README.md
```

## 👥 团队分工

> 完整分工细则见 **[`docs/roles.md`](./docs/roles.md)**，以下为速览。

| 角色 | 代号 | 负责人 | 核心职责 | 代码领地 |
|---|---|---|---|---|
| **Agent 工程师** | `A-Agent` | **[@Nekooo915](https://github.com/Nekooo915)** | LLM 客户端封装、Student / Director / Evaluator Agent、RAG 管线、LangGraph 状态机、**事件流生产者**（push 到 asyncio.Queue） | `backend/{agents,rag,llm,graph,prompts,schemas}` |
| **全栈工程师** | `B-Full` | **[@Traumere7](https://github.com/Traumere7)** | 前端课堂 UI 与诊断报告、**WebSocket 端到端**（前后端）、REST 路由、会话持久化、视觉与落地页 | `frontend/`、`backend/{api,db}` |
| **产品 / 评测** | `C-Prod` | **[@IST00](https://github.com/IST00)** | 立项书与产品展示材料、学生人设设计、学科迷思概念库、评估 Rubric、用户测试、Demo 视频 | `data/`、`docs/`、`backend/prompts/` |

### A ↔ B 内部契约（非对外 API）

- A 把 Agent 事件 push 到 `asyncio.Queue[AgentEvent]`（类型定义在 `backend/schemas/events.py`，B 维护）
- B 的 WS endpoint consume 该 queue，封装为对外 JSON Lines 帧推给前端
- 事件 schema 变更须两人连署 approve

### 主要交付阶段

| 阶段 | A-Agent | B-Full | C-Prod |
|---|---|---|---|
| **第一阶段** | LLMClient + 单学生 Agent + 教案 RAG + 学段特征库 | FastAPI 脚手架 + API 合约 + 前端脚手架 | 立项书 + 人设设计 + 样例教案 |
| **第二阶段** | Director 调度 + 事件流生产者 | WebSocket endpoint + 前端 client + 虚拟课堂 UI + 会话管理 | 迷思概念库 + Rubric 初版 |
| **第三阶段** | Evaluator Agent + 端到端联调 | 诊断报告页面 + 数据可视化 | 迷思库扩展 + 用户测试方案 |
| **第四阶段** | 性能与稳定性调优 | 品牌视觉 + 落地页 + 暗色模式 | 产品展示 PPT + Demo 视频 + 用户测试执行 |

## 🚦 协作 & 开发

- **协作规范**：[`CONTRIBUTING.md`](./CONTRIBUTING.md) — 分支策略、Commit 规范、PR 流程、冲突解决
- **分工细则**：[`docs/roles.md`](./docs/roles.md) — 每个角色的技术栈、目录所有权、跨界协作边界
- **任务看板**：<https://github.com/orgs/echoclass-team/projects/1>
- **Issue 列表**：<https://github.com/echoclass-team/EchoClass/issues>
- **API 合约**：[`docs/api_contract.md`](./docs/api_contract.md)
- **人设设计文档**：[`docs/persona_design.md`](./docs/persona_design.md)
- **立项书**：[`docs/proposal.md`](./docs/proposal.md)

### 当前 Issue 推进顺序

> ⚠️ **2026-04-25 转型后**：以下 issue 列表是转型前规划的旧版本，部分（#23 / #24 / #25 / #65 等）已随产品转型废弃或重新规划，待对齐 M2/M3/M4 路线图（详见 [`docs/PIVOT.md`](./docs/PIVOT.md)）。
>
> 实际推进以 GitHub Issues 为准。

**第一优先级：打通课堂实时链路**

1. **#21 总体集成协调**：冻结 sessions、WebSocket、AgentEvent、报告数据源等跨角色接口。
2. **#39 Sessions API / SQLite 持久化**：提供 `POST /api/sessions`、session store、messages 表，并桥接 #24 的 graph checkpoint；是 #25 / #26 / #29 / #31 的后端基础。
3. **#25 WebSocket / AgentEvent wire 协议**：实现 WS endpoint、JSON Lines 编码、全局事件顺序、chunk 顺序与错误处理；可与 #39 并行设计，最终 endpoint 依赖 #39。
4. **#65 DirectorDecision → AgentEvent adapter**：在 #25 字段稳定后，把 Director / graph 内部事件正式映射到可推送事件。
5. **#61 Setup 流程调整**：基于已合入的推荐学生接口，完成“教案 → 默认学段与默认学生 → 开始模拟”；开始课堂按钮最终依赖 #39 / #26。

**第二优先级：课堂体验与评估闭环**

6. **#26 虚拟课堂 UI / WS client**：可先用 mock UI 推进；真实联调依赖 #61 / #39 / #25 / #65。
7. **#27 学科迷思概念库 v1 + StudentAgent 接入**：为学生错误生成与后续评估提供可检索的学科迷思依据。
8. **#28 评估 Rubric + 评估框架文档**：定义 4 维度评估指标，为 EvaluatorAgent 和报告生成提供评分标准。
9. **#29 评估 Agent / 诊断报告生成后端**：依赖 #27、#28 与 #39，读取课堂消息、Director 历史和评估结果。
10. **#30 诊断报告前端页面**：依赖 #29，前期可用 mock report 做 UI。
11. **#40 迷思概念库扩展**：在 #27 v1 基础上扩展到 ≥50 条，覆盖全部 6 档学段。

**第三优先级：端到端打磨与展示**

12. **#31 端到端 Demo 联调**：依赖 setup、session、WS、adapter、classroom UI 与 report 链路稳定。
13. **#33 品牌视觉 / 首页 / 暗色模式**：可与主链路并行做基础设计，最终 polish 等 #26 / #30 页面稳定后完成。
14. **#32 用户测试方案**：设计面向 3 位师范生的测试任务、观察指标和访谈提纲。
15. **#34 用户测试执行**：在可演示链路稳定后执行测试并整理报告。
16. **#35 Demo 视频**：依赖可演示链路，完成 3 分钟脚本、录制、剪辑和发布。
17. **#36 产品展示 PPT / 立项书定稿 / QA 预案**：依赖 Demo 与核心链路稳定后收口。

### 新成员 Onboarding

1. 阅读本 README + [`CONTRIBUTING.md`](./CONTRIBUTING.md) + [`docs/roles.md`](./docs/roles.md)
2. 认领自己的 Role（A / B / C）
3. 从 Issue 列表里挑一个自己负责的任务，分配给自己
4. 按 [`CONTRIBUTING.md`](./CONTRIBUTING.md) 的流程开分支、写代码、开 PR

```bash
# 基于某个 Issue 一键建分支开工
gh issue develop <N> --repo echoclass-team/EchoClass --checkout
```

### 本地启动后端

详见 [`backend/README.md`](./backend/README.md)。快速开始：

```bash
cd backend
uv sync --extra dev                       # 安装依赖（需先装 uv：curl -LsSf https://astral.sh/uv/install.sh | sh）
cp .env.example .env                      # 填入 OPENAI_API_KEY 等
uv run uvicorn main:app --reload --port 8000
# 验证：curl http://localhost:8000/health        →  {"status":"ok"}
# 查看学段：curl http://localhost:8000/api/stages
# 查看人设：curl http://localhost:8000/api/personas
uv run pytest                             # 运行全部测试（当前 137 条）
```

### 本地启动前端

```bash
cd frontend
npm install                               # 首次安装依赖
npm run dev                               # 启动在 http://localhost:3000
```

前端默认连后端 `http://localhost:8000`，如需覆盖在 `frontend/.env.local` 设置：

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

页面入口（当前实现 + 规划中的 setup 调整）：

- `/` — 首页 + 本地教案库预览
- `/setup/stage` — 选择学段（旧 setup 流程）
- `/setup/config` — 选教案 + 选学生（旧 setup 流程）
- `/setup/lesson` → `/setup/students` — 规划中的教案优先 setup 流程（见 #61）
- `/classroom/demo` — 课堂演示（WebSocket 待接入）

### 常用命令

```bash
# 1v1 答疑陪练 demo（真实 LLM；含教案 → 学生提问 → 1v1 对话 → 总结）
uv run python scripts/try_qa_session.py --lesson math_p3_fraction --students 2 --questions 3

# 教案 RAG 完整管线冒烟（解析 → 抽取 → 索引；不依赖 1v1 流程）
uv run python scripts/try_lesson_rag.py

# 校验 18 个学生人设 JSON 的完整性（不调 LLM）
uv run python scripts/validate_personas.py
```

## 📜 License

MIT
