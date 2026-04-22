# 三人分工规范 · EchoClass

> 本文件是团队分工的唯一真相（Single Source of Truth）。
> Issue 里的 Owner 字段必须与本文一致，跨界改动前请在群里同步。

---

## 👤 Role A · Agent 工程师（后端大脑）

**代号**：`A-Agent`

**核心职责**：构建 EchoClass 的 AI 大脑——所有 LLM、Agent、RAG 逻辑。

### 技术栈

- Python 3.11、FastAPI、LangGraph、Pydantic v2
- LLM SDK：OpenAI 兼容接口（DeepSeek / Qwen / DashScope）
- 向量库：Chroma
- 测试：pytest + pytest-asyncio

### 代码所有权

```
backend/
├── agents/         # 学生 Agent、Director Agent、Evaluator Agent
├── rag/            # 教案解析、向量化、检索
├── llm/            # LLM 客户端封装（重试、限流、成本追踪）
├── graph/          # LangGraph 状态机定义
└── tests/agents/
```

### 分支前缀

`feat/agent-*`、`feat/rag-*`、`feat/graph-*`

### 每周核心产出

| 周 | 关键交付 |
|---|---|
| W1 | 单学生 Agent + 教案 RAG 跑通 |
| W2 | Director 多 Agent 调度 + WebSocket 流式 |
| W3 | 评估 Agent + 端到端集成 |
| W4 | 性能优化 + 稳定性 |

---

## 👤 Role B · 全栈工程师（面子 + API 粘合）

**代号**：`B-Full`

**核心职责**：用户看得到的一切 + 连接前后端的 API 层。

### 技术栈

- Next.js 14（App Router）、TypeScript、TailwindCSS、shadcn/ui
- 状态：Zustand；数据请求：TanStack Query
- 实时：原生 WebSocket + Vercel AI SDK 流式
- 图表：Recharts；图标：lucide-react
- 后端 API 层：FastAPI 路由（非 Agent 内部）

### 代码所有权

```
frontend/                    # 全部
backend/
├── api/                     # REST + WebSocket 路由
├── schemas/                 # Pydantic 请求/响应模型
├── db/                      # 会话存储（SQLite / 文件）
└── main.py
```

### 分支前缀

`feat/fe-*`、`feat/api-*`

### 每周核心产出

| 周 | 关键交付 |
|---|---|
| W1 | 前端脚手架 + 首页 + API 客户端封装 |
| W2 | 虚拟课堂 UI + WebSocket 消息流 |
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
├── pitch_deck.md            # 答辩 PPT 大纲
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
| W4 | 答辩 PPT + Demo 视频 + 3 位师范生试用 |

---

## 🤝 跨界协作边界

| 共享文件 / 边界 | 主 Owner | 规则 |
|---|---|---|
| `backend/main.py` | B | A 只能加 router 注册，改前说一声 |
| `backend/schemas/` | B | A 提需求，B 落实 |
| `backend/prompts/` | C + A | C 写初版，A review 后接入代码 |
| API 合约（`docs/api_contract.md`） | B | 先写 schema，A/C 基于此开发 |
| `pyproject.toml` / `package.json` | 谁加依赖谁加 | PR 里必须说明新增依赖理由 |
| `README.md` | 共同 | 改动大时先开 Issue 讨论 |

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

| 标签 | 含义 |
|---|---|
| `week-1` ~ `week-4` | 计划执行周次 |
| `agent` | Role A 负责 |
| `frontend` | Role B 负责 |
| `api` | Role B 负责（API 层） |
| `eval` | Role C 负责（评估相关） |
| `data` | Role C 负责（内容数据） |
| `docs` | 任何人都可能涉及，以 C 为主 |
| `infra` | 基建，多人协作 |
| `bug` | 修复问题 |
| `enhancement` | 功能增强 |
| `task` | 常规任务 |
