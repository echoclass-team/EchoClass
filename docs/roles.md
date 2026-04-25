# 三人分工规范 · EchoClass

> 本文件是团队分工的唯一真相（Single Source of Truth）。
> Issue 里的 Owner 字段必须与本文一致，跨界改动前请在群里同步。

---

## 👤 Role A · Agent 工程师（AI 大脑）

**代号**：`A-Agent`

**核心职责**：构建 EchoClass 的 AI 大脑——所有 LLM、Agent、RAG 逻辑，并向传输层（B）产出流式事件。

**不做**：不写 HTTP / WebSocket 路由本身（那是 B 的活）；不写 Pydantic 请求/响应外型（B 维护，A 提需求）。

### 技术栈

- Python 3.11、LangGraph、Pydantic v2（内部模型）
- LLM SDK：OpenAI 兼容接口（DeepSeek / Qwen / DashScope）、tenacity 重试
- 向量库：Chroma；嵌入：bge-small / text-embedding-v3
- 教案解析：pymupdf4llm
- 异步：asyncio（产生事件推到 `asyncio.Queue[AgentEvent]`）
- 测试：pytest + pytest-asyncio

### 代码所有权

```
backend/
├── agents/         # 学生 Agent、Director Agent、Evaluator Agent
├── rag/            # 教案解析、向量化、检索
├── llm/            # LLM 客户端封装（重试、限流、成本追踪）
├── graph/          # LangGraph 状态机定义、事件产生者
└── tests/agents/
```

### 分支前缀

`feat/agent-*`、`feat/rag-*`、`feat/graph-*`

### 每周核心产出

| 周 | 关键交付 |
|---|---|
| W1 | 单学生 Agent + 教案 RAG 跑通 |
| W2 | Director 多 Agent 调度 + 事件流产生者（推到 queue） |
| W3 | 评估 Agent + 端到端联调 |
| W4 | 性能优化 + 稳定性 + （stretch）ASR/TTS 接入 |

---

## 👤 Role B · 全栈工程师（传输层 + 界面）

**代号**：`B-Full`

**核心职责**：用户看得到的一切 + 连接前后端的完整传输链路（REST 与 WebSocket 两端）。

**不做**：不写 LLM / Agent / RAG 本身的逻辑（那是 A 的活）。

### 技术栈

**前端**：
- Next.js 14 (App Router)、TypeScript、TailwindCSS、shadcn/ui
- 状态：Zustand；数据请求：TanStack Query
- 实时：原生 WebSocket client + Vercel AI SDK（流式渲染）
- 图表：Recharts；图标：lucide-react

**后端传输层**：
- Python 3.11、FastAPI（REST 路由）
- WebSocket endpoint（FastAPI）：从 A 提供的 `asyncio.Queue` consume 事件→序列化为 JSON Lines 推给前端
- Pydantic v2（对外 schema）
- SQLite（会话 / 消息持久化）

### 代码所有权

```
frontend/                    # 全部
backend/
├── api/                     # REST 路由 + WebSocket endpoint
├── schemas/
│   ├── requests.py          # REST 请求/响应 Pydantic
│   └── events.py            # A↔B 内部事件类型（AgentEvent union）
├── db/                      # SQLite（会话 · 消息）
└── main.py                  # FastAPI 入口，router 挂载
```

### 分支前缀

`feat/fe-*`、`feat/api-*`、`feat/ws-*`

### 每周核心产出

| 周 | 关键交付 |
|---|---|
| W1 | 前端脚手架 + 首页 + API 客户端封装 + `schemas/events.py` 骨架 |
| W2 | WS endpoint（后）+ WS client（前）+ 虚拟课堂 UI + 会话管理 REST |
| W3 | 诊断报告页 + 会话历史 |
| W4 | Logo / 视觉打磨 + 落地页 + 暗色模式 |

---

## 👤 Role C · 产品 / 内容 / 评测（大脑 + 质检）

**代号**：`C-Prod`

**核心职责**：让产品**有内容、可衡量、能打动人**——三人小队里最易被低估但最决定成败的角色。

### 技术栈

- Python 脚本（数据清洗、JSON 校验）
- Markdown + draw.io/Figma（文档、PPT）
- 教育学知识：皮亚杰认知发展、Flanders 互动分析、学科迷思概念研究
- 可选加分：Prompt 工程、RAGAS 评测

### 所有权

```
data/
├── personas/                # 学生人设 JSON（6 个）
├── misconceptions/          # 迷思概念库（小学数学 50 条）
├── lesson_samples/          # 样例教案 PDF
└── eval_rubrics/            # 评估评分标准 JSON
docs/
├── proposal.md              # 立项书
├── pitch_deck.md            # 产品展示 PPT 大纲
├── demo_script.md           # Demo 视频脚本
├── user_test_plan.md        # 用户测试计划
└── references/              # 参考文献
backend/prompts/             # 共享：Prompt 模板（与 A 协作）
```

### 分支前缀

`feat/eval-*`、`feat/data-*`、`docs/*`

### 每周核心产出

| 周 | 关键交付 |
|---|---|
| W1 | 立项书 v1 + 6 个学生人设 + 评估框架设计 |
| W2 | 迷思概念库 20 条 + 评估 Prompt v1 + 样例教案 3 份 |
| W3 | 迷思库补齐 50 条 + 用户测试方案 |
| W4 | 产品展示 PPT + Demo 视频 + 3 位师范生试用 |

---

## 🤝 跨界协作边界

### 文件级所有权

| 共享文件 / 边界 | 主 Owner | 规则 |
|---|---|---|
| `backend/main.py` | B | **特例**：#W1-01 脚手架由 A 创建初版，合并后日常修改归 B；A 只能加 router 注册，改前说一声 |
| `backend/schemas/requests.py` | B | 对外 REST schema；A 提需求 |
| `backend/schemas/events.py` | B + A | 内部事件类型（A↔B 契约）；**任何改动必须两人连署 approve** |
| `backend/prompts/` | C + A | C 写初版，A review 后接入代码 |
| API 合约（`docs/api_contract.md`） | B | v0 已存在；后续改动需 A 与 B 都 approve |
| `pyproject.toml` / `package.json` | 谁加依赖谁加 | PR 里必须说明新增依赖理由 |
| `README.md` / `docs/roles.md` | 共同 | 改动大时先开 Issue 讨论 |

### WebSocket 分层职责（重要）

WebSocket 距离两端跨界，按层拆分所有权：

```
【前端 WebSocket client】— B
  │ 原生 WebSocket 、 重连 、心跳、事件订阅 UI
  ▼
【后端 WS endpoint】      — B（backend/api/ws.py）
  │ 连接管理、鉴权、消息序列化、心跳
  │ consume asyncio.Queue[AgentEvent]
  ▼
【事件产生者】              — A（backend/graph/, agents/）
  │ LangGraph 节点输出 → push 到 queue
  │ 事件类型在 backend/schemas/events.py（B+A 共同）
```

**谁接手规则**：
- A 发现需要新事件类型 → 先在 Issue / 群里提出 → B 更新 `events.py` + `api_contract.md` 同步 → 合并后 A 再写产生代码
- B 发现消息丢失 / 顺序问题 → 和 A 一起调试 queue / event loop

---

## 🗣️ 协作仪式（4 周）

| 活动 | 频率 | 时长 | 形式 |
|---|---|---|---|
| **每日站会** | 每天 | 15 min | 微信语音 / 文字：昨天/今天/阻塞 |
| **Sprint Planning** | 每周一 | 30 min | 过 Issue，领任务 |
| **Demo Day** | 每周五 | 30 min | 每人演示本周产出 |
| **PR Review** | 随时 | SLA 24h | 指派后 24h 内给反馈 |

---

## 🎯 任务领取流程

```bash
# 1. 浏览看板：https://github.com/orgs/echoclass-team/projects/1
# 2. 找符合自己 Role + 本周标签的 Issue
# 3. 分配给自己
gh issue edit <N> --repo echoclass-team/EchoClass --add-assignee @me

# 4. 基于 Issue 开分支
gh issue develop <N> --repo echoclass-team/EchoClass --checkout

# 5. 开工，按 CONTRIBUTING.md 走 PR 流程
```

---

## 📋 Issue 标签速查

| 标签 | 含义 | 典型 Owner |
|---|---|---|
| `week-1` ~ `week-4` | 计划执行周次 | — |
| `agent` | Agent / LLM / RAG / Graph 逻辑 | A |
| `frontend` | 前端 UI | B |
| `api` | 后端 REST / WS 路由层 | B |
| `eval` | 评估 / 报告 / 用户测试 | C |
| `data` | 人设库 / 迷思库 / 样例教案 | C |
| `docs` | 文档 | C 为主，任何人可改 |
| `infra` | 构建 / 部署 / 脚手架 | A 或 B |
| `bug` | 修复问题 | 按模块 |
| `enhancement` | 功能增强 | 按模块 |
| `task` | 常规任务 | — |
