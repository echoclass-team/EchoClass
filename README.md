# EchoClass

> AI-powered virtual classroom for pre-service teachers.
> 师范生虚拟学生陪练 Agent —— 让每位未来的老师都有无限次"试讲"机会。

参赛项目：**华东师范大学开发者大赛 2026 · 大语言模型创新应用开发赛道**
赛事官网：<https://developer.ecnu.edu.cn/competition2026/>

---

## ✨ 项目简介

EchoClass 是一个基于多智能体的"虚拟课堂"系统：师范生上传教案后，系统生成多位性格/学力各异的虚拟学生（由 LLM 扮演），进行沉浸式课堂演练，并在课后输出量化的教学能力诊断报告。

核心亮点：

- **Director Agent 调度**：避免多学生同时发言的混乱，按真实课堂节奏触发互动
- **基于教育学理论的学生人设**：皮亚杰认知阶段 + 学科常见迷思概念库，错得真实
- **多维诊断报告**：教学设计 / 课堂互动 / 语言表达 / 课堂管理（参考 Flanders 互动分析）

## 🏗️ 技术栈

按层组织，括号内为主要负责角色：

| 层 | 技术 | Owner |
|---|---|---|
| **前端** | Next.js 14 (App Router) · TypeScript · TailwindCSS · shadcn/ui · Zustand · TanStack Query · Vercel AI SDK · Recharts | **B** |
| **传输 / Protocol** | FastAPI REST · WebSocket（JSON Lines）· CORS · 鉴权 | **B** |
| **Agent / Graph** | LangGraph（有状态图）· asyncio.Queue（事件流式） | **A** |
| **LLM** | DeepSeek-V3 / Qwen2.5（OpenAI 兼容接口）· tenacity 重试 | **A** |
| **RAG** | Chroma · bge-small 或 text-embedding-v3 · pymupdf4llm | **A** |
| **持久化** | SQLite（会话 / 消息） | **B** |
| **数据 / 内容** | JSON Schema · 人设库 · 迷思概念库 · Rubric | **C** |
| **测试** | pytest + pytest-asyncio（后）· Vitest + Playwright（前，stretch） | A / B |
| **ASR / TTS** · _W4 stretch_ | 阿里云 Paraformer / CosyVoice | A |

## 📁 目录结构（规划中）

```
EchoClass/
├── backend/                 # Python · FastAPI + LangGraph
│   ├── agents/              # 学生 / Director / Evaluator Agent
│   ├── rag/                 # 教案解析、向量化、检索
│   ├── llm/                 # LLM 客户端封装
│   ├── graph/               # LangGraph 状态机
│   ├── api/                 # REST + WebSocket 路由
│   ├── schemas/             # Pydantic 请求/响应模型
│   ├── db/                  # 会话持久化（SQLite）
│   ├── prompts/             # Prompt 模板
│   └── tests/
├── frontend/                # TypeScript · Next.js 14 + shadcn/ui
├── data/
│   ├── personas/            # 学生人设 JSON
│   ├── misconceptions/      # 迷思概念库
│   ├── lesson_samples/      # 样例教案 PDF
│   └── eval_rubrics/        # 评估评分标准
├── docs/
│   ├── roles.md             # 三人分工规范
│   ├── api_contract.md      # API 合约
│   ├── proposal.md          # 立项书
│   ├── pitch_deck.md        # 答辩 PPT 大纲
│   └── user_test_plan.md    # 用户测试方案
├── .github/                 # PR / Issue 模板
├── CONTRIBUTING.md          # 协作规范
└── README.md
```

## 👥 团队分工

> 完整分工细则见 **[`docs/roles.md`](./docs/roles.md)**，以下为速览。

| 角色 | 代号 | 负责人 | 核心职责 | 代码领地 |
|---|---|---|---|---|
| **Agent 工程师** | `A-Agent` | TBD | LLM 客户端、学生 / Director / Evaluator Agent、RAG、LangGraph 状态机、**产生流式事件**（push 到 asyncio.Queue） | `backend/{agents,rag,llm,graph}` |
| **全栈工程师** | `B-Full` | TBD | 前端课堂 / 报告 UI、**WebSocket 端到端**（前端 client + 后端 endpoint）、REST 路由、会话持久化、落地页与视觉打磨 | `frontend/`、`backend/{api,schemas,db}` |
| **产品 / 评测** | `C-Prod` | TBD | 立项书与答辩材料、学生人设库、迷思概念库、评估 Rubric、用户测试、Demo 视频 | `data/`、`docs/`、`backend/prompts/` |

**A ↔ B 内部契约**（非对外 API）：
- A 把 Agent 事件 push 到 `asyncio.Queue[AgentEvent]`（类型定义在 `backend/schemas/events.py`，B 维护）
- B 的 WS endpoint consume 该 queue，封装为对外 JSON Lines 帧推给前端
- 事件 schema 变更须两人连署 approve

**每周核心交付一览**：

| 周 | A-Agent | B-Full | C-Prod |
|---|---|---|---|
| W1 | 单学生 Agent + 教案 RAG | 前端脚手架 + API 合约 v1 | 立项书 v1 + 6 个人设 |
| W2 | Director 调度 + **事件流产生者** | **WS endpoint + 前端 client** + 虚拟课堂 UI + 会话管理 | 迷思库 v1（20 条）+ Rubric |
| W3 | 评估 Agent + 端到端联调 | 诊断报告页 | 迷思库 50 条 + 用户测试方案 |
| W4 | 性能 / 稳定性 | Logo / 落地页 / 暗色模式 | 答辩 PPT + Demo 视频 + 用户测试 |

## 🚦 协作 & 开发

- **协作规范**：[`CONTRIBUTING.md`](./CONTRIBUTING.md) — 分支策略、Commit 规范、PR 流程、冲突解决
- **分工细则**：[`docs/roles.md`](./docs/roles.md) — 每个角色的技术栈、目录所有权、周度产出、跨界协作边界
- **任务看板**：<https://github.com/orgs/echoclass-team/projects/1>
- **Issue 列表**：<https://github.com/echoclass-team/EchoClass/issues>（25 个任务按 W1–W4 编号）
- **API 合约**（v0 草案已就位）：[`docs/api_contract.md`](./docs/api_contract.md)
- **W1 阶段性测试指引**：[`docs/w1_smoke_test.md`](./docs/w1_smoke_test.md) — 后端脚手架 + LLMClient + ChatECNU 集成验证

### 新成员 Onboarding

1. 阅读本 README + [`CONTRIBUTING.md`](./CONTRIBUTING.md) + [`docs/roles.md`](./docs/roles.md)
2. 认领自己的 Role（A / B / C）
3. 从 `week-1` 标签的 Issue 里挑一个自己负责的，分配给自己
4. 按 [`CONTRIBUTING.md`](./CONTRIBUTING.md) 的流程开分支、写代码、开 PR

```bash
# 基于某个 Issue 一键建分支开工
gh issue develop <N> --repo echoclass-team/EchoClass --checkout
```

### 本地启动后端

详见 [`backend/README.md`](./backend/README.md)。快速开始：

```bash
cd backend
uv sync --extra dev          # 安装依赖（需先装 uv：curl -LsSf https://astral.sh/uv/install.sh | sh）
cp .env.example .env          # 填入 OPENAI_API_KEY 等
uv run uvicorn main:app --reload --port 8000
# 验证：curl http://localhost:8000/health  →  {"status":"ok"}
uv run pytest                 # 运行测试
```

## 📅 里程碑

- [ ] **Week 1** · 脚手架 + 单学生 Agent + 教案解析 Demo（[W1 Issues](https://github.com/echoclass-team/EchoClass/issues?q=is%3Aissue+label%3Aweek-1)）
- [ ] **Week 2** · Director + 多学生并发 + 前端课堂 UI（[W2 Issues](https://github.com/echoclass-team/EchoClass/issues?q=is%3Aissue+label%3Aweek-2)）
- [ ] **Week 3** · 评估模块 + 报告 + 小学数学迷思库（50 条）（[W3 Issues](https://github.com/echoclass-team/EchoClass/issues?q=is%3Aissue+label%3Aweek-3)）
- [ ] **Week 4** · 打磨 + Demo 视频 + 答辩 PPT（[W4 Issues](https://github.com/echoclass-team/EchoClass/issues?q=is%3Aissue+label%3Aweek-4)）

## 📜 License

MIT
