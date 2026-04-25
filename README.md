# EchoClass

> AI-powered virtual classroom for pre-service teachers.
> 师范生虚拟课堂陪练系统 —— 让未来的教师在走上讲台前多试几次讲。

参赛项目：**华东师范大学开发者大赛 2026 · 大语言模型创新应用开发赛道**
赛事官网：<https://developer.ecnu.edu.cn/competition2026/>

---

## ✨ 项目简介

### 背景

师范生在正式走上讲台之前，缺乏安全、低成本、可重复的练习场景：

- **真人试讲难**：组织一节真实课堂代价高，一次课只能留下 40 分钟录音和模糊印象
- **反馈滞后**：导师点评稀缺，难以对同一教学环节做 A / B 对比
- **学生反应千差万别**：薄弱生、优等生、走神生、爱跑题生——真实课堂上永远只能遇到一种组合
- **教案到实战的鸿沟**：写教案时计划详尽，一到课堂上就发现"这个概念孩子根本听不懂"

### 使用流程

EchoClass 是一个基于多 Agent 协作的虚拟课堂陪练系统：

1. **上传教案** — 支持 PDF / Markdown / TXT，系统自动解析并抽取学科、学段、教学目标、知识点、难点
2. **选择学段与学生** — 从小学低年级到高中共 6 档学段、每档 3 种典型学生（共 18 个虚拟学生人设），组建虚拟班级
3. **开始模拟授课** — 师范生以"老师"身份和虚拟学生互动，每个学生按其人设和学段认知边界实时回答、提问、走神或沉默
4. **课后诊断报告** — 从教学设计、课堂互动、语言表达、课堂管理四个维度，输出量化评分与改进建议

### 关键设计点

- **双层建模（学段共性 × 个体差异）**：先用 6 档学段特征库（基于皮亚杰认知发展阶段、维果茨基最近发展区、埃里克森心理社会理论、教育部《中小学心理健康教育指导纲要》）约束学生的认知上限，再叠加个体人设（性格、口头禅、学业水平、迷思倾向）。这避免了 LLM 常见的"小学一年级学生开口就讲微积分"的失真问题。

- **Director Agent 调度**：不让所有虚拟学生同时发言。Director 根据课堂节奏、学生注意力、老师语气，决定下一个该谁发言、该不该提问、该不该走神。

- **学科迷思概念库驱动的错误生成**：薄弱学生的错误不是随机的，而是从学科常见迷思概念库里挑选（如小学分数加法常把分子分母分别相加），让师范生在练习中识别并应对真实教学难点。

- **多维度评估（参考 Flanders 互动分析体系）**：教学设计、课堂互动、语言表达、课堂管理四维评分 + 文字点评。

- **教案 RAG 检索**：上传的教案会被解析、切片、向量化并索引，学生回复会围绕教案实际内容展开。

## 📌 当前进度

截至本次更新（第一阶段主体已完成，第二阶段核心链路推进中）：

**后端（A-Agent）**

- ✅ FastAPI 脚手架 + CORS + `/health`
- ✅ LLMClient 封装（ChatECNU ecnu-max，OpenAI 兼容接口 + tenacity 重试 + token 日志）
- ✅ StudentAgent 原型（人设驱动的结构化回复，Jinja2 模板 + JSON 解析）
- ✅ 18 个学生人设 JSON + 完整 18 字段 Persona 模型
- ✅ 6 档学段认知特征库（StageProfile，基于皮亚杰 / 维果茨基 / 埃里克森）
- ✅ StudentAgent × StageProfile 联调（学段共性层 + 个体差异层）
- ✅ 教案 RAG 管线：parser（pymupdf4llm）→ extractor（LLM 结构化抽取）→ indexer（Chroma 切片向量化）
- ✅ REST API：`/api/lessons/upload|{id}` · `/api/lessons/{id}/recommended-personas` · `/api/stages[/{id}]` · `/api/personas[/{name_or_id}]`
- ✅ **统一响应包络 `ApiResponse`**：`{code, message, data, request_id}`，错误也走同一结构（全局 HTTPException handler）
- ✅ 6 份跨学段样例教案（小低 / 小中 / 小高 / 初低 / 初高 / 高中，Markdown + PDF + 解析预期）
- ✅ DirectorAgent 多学生调度器（规则层硬约束 + LLM 软判断）
- ✅ LangGraph 课堂核心状态机（A 侧 graph core + internal AgentEvent + checkpoint）
- ✅ 137 条单元 & 集成测试全绿
- ⏳ WebSocket / sessions / AgentEvent adapter 端到端集成（第二阶段）
- ⏳ EvaluatorAgent 与诊断报告链路（第三阶段）

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

- ✅ 立项书 v4 终极答辩论证版
- ✅ 学生人设设计文档
- ✅ 6 份跨学段样例教案
- ⏳ 学科迷思概念库
- ⏳ 评估 Rubric + Flanders 互动分析表

## 🏗️ 技术栈

| 层 | 技术 | Owner |
|---|---|---|
| **前端** | Next.js 14（App Router）· TypeScript · TailwindCSS · shadcn/ui · Zustand · TanStack Query · Recharts | **B** |
| **API / 协议** | FastAPI · WebSocket（JSON Lines）· REST · CORS · uv | **B** |
| **Agent 编排** | LangGraph（有状态图）· asyncio.Queue（事件流生产者-消费者） | **A** |
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
├── backend/                     # Python 3.11+ · FastAPI + LangGraph
│   ├── agents/                  # StudentAgent / DirectorAgent（已完成）· EvaluatorAgent（规划中）
│   ├── rag/                     # 教案解析、抽取、切片、Chroma 索引
│   │   ├── parser.py            # PDF / MD / TXT → 纯文本
│   │   ├── extractor.py         # LLM 抽取 subject/grade/topic/objectives/key_points/difficult_points
│   │   └── indexer.py           # 500 token 切片 + Chroma 向量化
│   ├── llm/                     # LLMClient 封装（chat / stream + 重试 + 日志）
│   ├── graph/                   # LangGraph 课堂核心状态机 + checkpoint
│   ├── api/                     # REST + WebSocket 路由
│   │   ├── lessons.py           # POST /api/lessons/upload · GET /api/lessons/{id} · GET /api/lessons/{id}/recommended-personas
│   │   ├── stages.py            # GET /api/stages · GET /api/stages/{id}
│   │   └── personas.py          # GET /api/personas · GET /api/personas/{name_or_id}
│   ├── schemas/                 # Pydantic 模型
│   │   ├── stage.py             # StageProfile（学段认知特征）
│   │   ├── student.py           # Persona / ClassroomContext / StudentReply
│   │   ├── lesson.py            # LessonMeta / LessonRecord / RecommendedPersonasData
│   │   └── events.py            # graph internal AgentEvent（WS wire 格式待 #25 对齐）
│   ├── db/                      # 会话持久化（SQLite，规划中）
│   ├── prompts/                 # Jinja2 Prompt 模板
│   │   ├── student.j2           # 学生 Agent（学段共性 + 个体人设叠加）
│   │   ├── director.j2          # Director Agent 多学生调度
│   │   └── extractor.j2         # 教案元数据抽取
│   ├── scripts/                 # 冒烟测试脚本
│   └── tests/                   # pytest 单元与集成测试
├── frontend/                    # TypeScript · Next.js 14 + TailwindCSS
│   ├── src/app/                 # App Router：首页 / setup / classroom / lessons
│   ├── src/components/setup/    # Setup 流程（学段 / 教案 / 人设）
│   ├── src/lib/api/             # apiFetch 客户端（ApiResponse envelope + ApiError）
│   ├── src/lib/setup-storage.ts # 本地教案库 localStorage 持久化
│   └── src/types/               # Stage / Persona / Lesson 类型（严格对齐后端）
├── data/
│   ├── stage_profiles/          # 6 档学段认知特征 JSON（P1-P2 / P3-P4 / P5-P6 / J1-J2 / J3 / H1-H3）
│   ├── personas/                # 18 个学生人设 JSON（每学段 3 个：优秀 / 中等 / 薄弱）
│   ├── lesson_samples/          # 样例教案（PDF + Markdown + 解析预期元数据）
│   ├── misconceptions/          # 学科迷思概念库（规划中）
│   └── eval_rubrics/            # 评估评分标准（规划中）
├── docs/
│   ├── roles.md                 # 三人分工细则
│   ├── api_contract.md          # API 合约
│   ├── persona_design.md        # 人设设计文档
│   ├── proposal.md              # 立项书
│   └── pitch_deck.md            # 答辩大纲
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
| **产品 / 评测** | `C-Prod` | **[@IST00](https://github.com/IST00)** | 立项书与答辩材料、学生人设设计、学科迷思概念库、评估 Rubric、用户测试、Demo 视频 | `data/`、`docs/`、`backend/prompts/` |

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
| **第四阶段** | 性能与稳定性调优 | 品牌视觉 + 落地页 + 暗色模式 | 答辩 PPT + Demo 视频 + 用户测试执行 |

## 🚦 协作 & 开发

- **协作规范**：[`CONTRIBUTING.md`](./CONTRIBUTING.md) — 分支策略、Commit 规范、PR 流程、冲突解决
- **分工细则**：[`docs/roles.md`](./docs/roles.md) — 每个角色的技术栈、目录所有权、跨界协作边界
- **任务看板**：<https://github.com/orgs/echoclass-team/projects/1>
- **Issue 列表**：<https://github.com/echoclass-team/EchoClass/issues>
- **API 合约**：[`docs/api_contract.md`](./docs/api_contract.md)
- **人设设计文档**：[`docs/persona_design.md`](./docs/persona_design.md)
- **立项书**：[`docs/proposal.md`](./docs/proposal.md)

### 当前 Issue 推进顺序

> 以 GitHub Issues 为准；本节只记录当前推荐顺序和关键依赖，避免在评论中分散维护。

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
17. **#36 答辩 PPT / 立项书定稿 / QA 预案**：依赖 Demo 与核心链路稳定后收口。

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
# 冒烟测试 — StudentAgent 在不同人设下的回复
uv run python scripts/try_student_agent.py

# 冒烟测试 — DirectorAgent 多学生调度
uv run python scripts/try_director.py

# 冒烟测试 — 学段特征对生成回复的约束效果
uv run python scripts/try_stage_profile.py

# 冒烟测试 — 教案 RAG 完整管线（解析 → 抽取 → 索引）
uv run python scripts/try_lesson_rag.py
```

## 📜 License

MIT
