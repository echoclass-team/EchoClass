# 三人分工规范 · EchoClass

> 本文件是团队分工的唯一真相（Single Source of Truth）。
> Issue 里的 Owner 字段必须与本文一致，跨界改动前请在群里同步。
>
> **当前阶段**：M1 已收尾、M2 进行中（项目已转型为 **1v1 答疑陪练**，详见 [`proposal.md`](./proposal.md)）。
> **最后更新**：2026-04-25

---

## 👤 Role A · Agent 工程师（AI 大脑）

**代号**：`A-Agent`

**核心职责**：构建 EchoClass 的 AI 大脑——所有 LLM、StudentAgent、RAG 逻辑、QASession 编排，并向传输层（B）产出 1v1 流式事件（`StudentStreamEvent`）。

**不做**：不写 HTTP / WebSocket 路由本身（那是 B 的活）；不写 Pydantic 请求/响应外型（B 维护，A 提需求）。

### 技术栈

- Python 3.11、Pydantic v2（内部模型）、Jinja2（Prompt 模板）
- LLM SDK：OpenAI 兼容接口（ChatECNU ecnu-max 默认；可切 DeepSeek / Qwen）、tenacity 重试
- 向量库：Chroma；嵌入：bge-small / text-embedding-v3
- 教案解析：pymupdf4llm
- 异步：asyncio（流式 chunk 经 `stream_in_dialog` 产出 `StudentStreamEvent`）
- 测试：pytest + pytest-asyncio（mock LLM 不走网络）

### 代码所有权

```
backend/
├── agents/         # StudentAgent（generate_questions / respond_in_dialog / stream_in_dialog）
├── services/       # QASession（1v1 答疑会话编排：问题队列 + 对话状态机）
├── rag/            # parser / extractor / indexer + misconceptions（迷思匹配）+ qa_examples（few-shot 选择器）
├── llm/            # LLMClient 封装（chat / stream + 重试 + token 日志）
├── prompts/        # Jinja2 模板：student_ask / student_chat / student_check / extractor
│                   #   （C-Prod 写初版，A-Agent review 后接入代码）
├── schemas/        # 内部 Pydantic：student / dialog / question / misconception / stage / lesson
└── tests/agents/   tests/services/   tests/rag/
```

> 注：`backend/graph/` 是旧多 Agent 编排时代的空目录，无 LangGraph 依赖。M2 不会复用。

### 分支前缀

`feat/agent-*`、`feat/rag-*`、`feat/qa-*`

### M1 / M2 关键交付

| 里程碑 | 状态 | 关键交付 |
|---|---|---|
| **M1** | ✅ 已完成 | StudentAgent.generate_questions（宽生成 + self-check + 多样性筛选）；StudentAgent.respond_in_dialog 多轮对话；StudentAgent.stream_in_dialog 流式（含 `[懂了]` HOLDBACK 缓冲）；教案 RAG（parser/extractor/indexer）；迷思 RAG（match_misconceptions）；qa_examples few-shot 选择器；QASession 骨架；96+ 单元/集成测试全绿 |
| **M2** | 🚧 进行中 | QASession 端到端打磨（多轮 / 切换学生 / 放弃）；流式 `[懂了]` 在长对话下的稳定性回归；与 B 共定 WebSocket 1v1 事件 schema（`schemas/events.py`）；迷思命中率 / 脚手架层数等评估指标的可计算化（与 C 协同） |
| **M3** | 📋 计划 | 答疑后反馈 Agent（基于对话日志做迷思命中识别、脚手架质量打分）；性能 / token 成本调优；（stretch）ASR / TTS 接入 |

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
- WebSocket endpoint（FastAPI）：consume A 的 `stream_in_dialog` async generator → 序列化为 JSON Lines 推给前端（1v1 单流，无多 Agent 并发）
- Pydantic v2（对外 schema，含统一 `ApiResponse` 包络）
- SQLite（会话 / 对话历史 / 问题记录持久化）

### 代码所有权

```
frontend/                    # 全部
backend/
├── api/                     # REST 路由（lessons / stages / personas / sessions）+ WebSocket endpoint（M2）
├── schemas/
│   ├── api.py               # REST 请求/响应 Pydantic（含统一 ApiResponse 包络）
│   └── events.py            # A↔B 内部 1v1 流式事件类型（M2 待新增）
├── db/                      # SQLite（会话 · 对话历史 · 问题记录）
└── main.py                  # FastAPI 入口，router 挂载
```

### 分支前缀

`feat/fe-*`、`feat/api-*`、`feat/ws-*`

### M1 / M2 关键交付

| 里程碑 | 状态 | 关键交付 |
|---|---|---|
| **M1** | ✅ 已完成 | FastAPI 脚手架 + CORS + `/health`；统一 `ApiResponse` 响应包络（含 `request_id` 与全局 HTTPException handler）；REST：`/api/lessons/upload\|{id}` · `/api/stages[/{id}]` · `/api/personas[/{name_or_id}]`；前端 Next.js 14 脚手架 + Setup 三段式（学段 → 教案+学生 → 课堂演示骨架）；`apiFetch` 统一 client（envelope 解析 + ApiError）；本地教案库 localStorage 暂存 |
| **M2** | 🚧 进行中 | WebSocket endpoint（后）+ WS client（前）：1v1 流式答疑（消费 A 的 `stream_in_dialog`）；前端 1v1 答疑 UI（提问列表 → 选题 → 流式对话 + `[懂了]` 视觉处理）；`/api/sessions` REST（创建 / 详情 / 结束）；SQLite 持久化（会话 · 对话历史 · 问题记录）；shadcn/ui 组件化升级（Toast / Skeleton 替换手写） |
| **M3** | 📋 计划 | 答疑反馈页可视化（迷思命中高亮、轮次拆解、改进建议卡片）；会话历史与个人成长曲线；落地页 / 视觉打磨 / 暗色模式 |

---

## 👤 Role C · 产品 / 内容 / 评测（大脑 + 质检）

**代号**：`C-Prod`

**核心职责**：让产品**有内容、可衡量、能打动人**——三人小队里最易被低估但最决定成败的角色。

### 技术栈

- Python 脚本（数据清洗、JSON 校验）
- Markdown + draw.io/Figma（文档、PPT）
- 教育学知识：皮亚杰认知发展、维果茨基最近发展区与脚手架、学科迷思概念研究
- 可选加分：Prompt 工程、答疑专项评估指标设计

### 所有权

```
data/
├── personas/                # 学生人设 JSON（18 个：6 学段 × 优秀/中等/薄弱）+ _schema.json
├── misconceptions/          # 学科迷思概念库（21 份：覆盖小初高 × 数/理/化/生/语文/英语/史地政）+ _schema.json
├── stage_profiles/          # 6 学段共性认知特征 JSON（与 A 共享）
├── lesson_samples/          # 跨学段样例教案 PDF + Markdown + 解析期望 meta（M1 已交付 6 份）
└── eval_rubrics/            # 答疑专项评估评分标准（M2 起草）
docs/
├── proposal.md              # 立项书
├── persona_design.md        # 学生人设设计文档
├── pitch_deck.md            # 产品展示 PPT 大纲（M3）
├── demo_script.md           # Demo 视频脚本（M3）
├── user_test_plan.md        # 用户测试计划（M2 起草）
└── references/              # 参考文献
backend/prompts/             # 共享：Jinja2 Prompt 模板（C 写初版，A review 后接入代码）
```

### 分支前缀

`feat/eval-*`、`feat/data-*`、`docs/*`

### M1 / M2 关键交付

| 里程碑 | 状态 | 关键交付 |
|---|---|---|
| **M1** | ✅ 已完成 | 立项书 v1（1v1 答疑陪练）；6 学段 stage_profile JSON；18 个学生人设 JSON + 完整 schema 校验脚本；21 份学科迷思概念库 JSON；6 份跨学段样例教案（小低/小中/小高/初低/初高/高中，PDF + MD + meta）；6 学段 ask/chat few-shot 范例集合（与 A 协作落入 `rag/qa_examples`）；学生 prompt 模板 student_ask / student_chat / student_check 初版（与 A 共建） |
| **M2** | 🚧 进行中 | 答疑专项评估 Rubric 初版（候选维度：迷思命中率、脚手架层数、共情语数量、平均轮次、`self_resolved` 率）；评估 prompt v1（让 LLM 对完整 session 做诊断）；用户测试方案（招募标准、测试任务卡、反馈表）；2-3 段答疑示范片段录制（用于 demo 与 prompt 调优）；persona_design.md 与 misconceptions schema 的对齐与修订 |
| **M3** | 📋 计划 | 真人师范生用户测试 × 5+ 轮；测试报告与改进清单；答辩 PPT（pitch_deck.md）+ Demo 视频脚本；迷思库覆盖度补齐（按用户测试反馈补充） |

---

## 🤝 跨界协作边界

### 文件级所有权

| 共享文件 / 边界 | 主 Owner | 规则 |
|---|---|---|
| `backend/main.py` | B | **特例**：脚手架由 A 创建初版，合并后日常修改归 B；A 只能加 router 注册，改前说一声 |
| `backend/schemas/api.py` | B | 对外 REST schema（含 `ApiResponse` 包络）；A 提需求 |
| `backend/schemas/events.py` | B + A | 内部 1v1 流式事件类型（A↔B 契约，M2 待新增）；**任何改动必须两人连署 approve** |
| `backend/prompts/` | C + A | C 写初版，A review 后接入代码 |
| API 合约（`docs/api_contract.md`） | B | 后续改动需 A 与 B 都 approve |
| `data/personas/_schema.json` | C | 字段增删需通知 A，避免 Persona 模型不兼容 |
| `pyproject.toml` / `package.json` | 谁加依赖谁加 | PR 里必须说明新增依赖理由 |
| `README.md` / `docs/roles.md` / `docs/proposal.md` | 共同 | 改动大时先开 Issue 讨论 |

### WebSocket 分层职责（1v1 流式版，M2 落地）

相比转型前的多 Agent 事件队列，1v1 答疑陪练的流式链路更直接：A 暴露一个 async generator（`StudentAgent.stream_in_dialog`），B 把它逐 chunk 序列化成 JSON Lines 推给前端。

```
【前端 WebSocket client】— B
  │ 原生 WebSocket、断线重连、心跳、流式渲染（含 [懂了] 视觉处理）
  ▼
【后端 WS endpoint】      — B（backend/api/ws.py，M2 待新增）
  │ 连接管理、鉴权（token）、消息序列化、心跳
  │ async for event in agent.stream_in_dialog(...): ws.send_text(event.model_dump_json())
  ▼
【流式生产者】              — A（backend/agents/student.py）
  │ stream_in_dialog 产出 StudentStreamEvent：
  │   - delta(text=...)   # 0..N 个，已剥离末尾 16 字符 holdback
  │   - final(result=DialogReplyResult)   # 最后一个，含 self_resolved
  │ 事件 schema 定义在 backend/schemas/dialog.py（已存在）+ schemas/events.py（M2 待补 WS 包装）
```

**谁接手规则**：
- A 发现需要新事件类型（如 `error` / `interrupt`）→ 先在 Issue / 群里提出 → B 更新 `events.py` + `api_contract.md` 同步 → 合并后 A 再写产生代码
- B 发现消息丢失 / 顺序问题 → 和 A 一起调试 holdback 缓冲、stream 异常处理

---

## 🗣️ 协作仪式

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
| `m1` / `m2` / `m3` | 里程碑归属 | — |
| `agent` | StudentAgent / LLM / RAG / QASession 逻辑 | A |
| `frontend` | 前端 UI | B |
| `api` | 后端 REST / WS 路由层 | B |
| `eval` | 评估 / 报告 / 用户测试 | C |
| `data` | 人设库 / 迷思库 / 样例教案 | C |
| `docs` | 文档 | C 为主，任何人可改 |
| `infra` | 构建 / 部署 / 脚手架 | A 或 B |
| `bug` | 修复问题 | 按模块 |
| `enhancement` | 功能增强 | 按模块 |
| `task` | 常规任务 | — |
