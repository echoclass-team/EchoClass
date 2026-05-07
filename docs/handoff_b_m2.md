# B-Full M2 交接书

> **From**: A-Agent (@Nekooo915)
> **To**: B-Full (@Traumere7)
> **范围**: M2 阶段（前端 1v1 答疑陪练 UI + WS 客户端 + REST 路由）
> **关联 Issue**: #71（协议）· #72（前端 UI）
>
> **前置状态**：PR #77（协议冻结）· PR #78（C 端转型清理 + Persona schema v1.1）均已合入 main，协议层可直接动工

---

## 0. TL;DR

A 端已交付 M1 全套后端能力 + M2 流式输出 + WS 协议冻结（#77）。**协议层已稳定，可直接动工。** B 端在 M2 需要做三件事：

1. **后端 REST 包装** — `POST /api/qa-sessions` 等 1-2 个新接口
2. **前端 WS 客户端** — `frontend/lib/qa-ws.ts`（已有权威 schema：`backend/schemas/ws_events.py`）
3. **微信式 1v1 答疑 UI** — setup 流程 + 多对话切换 + summary 页

A 端在 M2 后续会配合的事：

- 协议有缺字段 → 改 `schemas/ws_events.py` 与 `docs/api_contract.md`
- 提供 mock WS server（`backend/scripts/mock_ws_server.py`）让你不必等真后端
- 实现 `backend/api/qa_ws.py` endpoint（虽是 B 领地，但 #71 issue 文案授权 A 写）

---

## 1. A 端目前已交付的能力（你能用的全部）

### 1.1 已合入 main 的 PR

| PR | 作者 | 内容 | 重要度 |
|---|---|---|---|
| #74 | A | 1v1 答疑陪练 M1 完整闭环（StudentAgent + QASession） | 🔴 核心 |
| #75 | A | StudentAgent 流式输出 `stream_in_dialog` | 🔴 核心 |
| #76 | A | 分平台后端使用文档（mac/linux + windows） | 🟢 参考 |
| **#77** | **A** | **QA WebSocket 协议冻结（协议已稳定，可直接对接）** | 🔴 **解锁本交接书所有任务** |
| **#78** | **C** | **转型后清理：persona schema v1.1（18→14 字段）+ proposal/roles/persona_design 全面对齐 1v1 答疑陪练定位** | 🟡 影响 Persona 字段 |

### 1.2 后端核心 API（你直接 import 用）

```python
# 服务层（业务编排，B 端 REST 直接包装这一层）
from services.qa_session import QASession, DialogStatus, ResolutionSource

# Agent（一般你不直接调，QASession 内部会调）
from agents.student import StudentAgent

# Pydantic 模型（一定会用到）
from schemas.lesson import LessonMeta
from schemas.question import StudentQuestion
from schemas.dialog import DialogMessage, DialogReplyResult, StudentStreamEvent
from schemas.student import Persona, PersonaSummary  # v1.3: 13 个核心字段
from schemas.ws_events import WsClientEvent, WsServerEvent, ...  # PR #77 已合入
```

> **Persona schema v1.3（M3 起）**：在 v1.1 基础上再移除 3 个字段——`personality` / `catchphrases` / `family_background`。人设质感由 `speech_style` + `behavior_traits` + `theory_anchors` + `summary` 联合承载。**对 B 端 WS 协议无破坏性影响**：`WsStudentInfo` 6 字段全部保留。前端 `PersonaDetail` 类型已同步精简（`frontend/src/types/persona.ts`）。
>
> **Persona schema v1.1（#78 已合）**：移除 4 个未被消费的死字段——`cognitive_stage` / `interaction_frequency` / `emotional_tendency` / `learning_motivation`（认知阶段由 `stage.piaget_stage` 统一约束）。

### 1.3 `QASession` API 速查（B 端 REST 调这些）

```python
session = QASession(...)              # 由工厂创建
await session.spawn(persona_ids, lesson_meta, count_per_student=3)
                                      # 学生集体生成问题填入队列
session.next_pending() -> Dialog | None
                                      # 弹出下一个待解答 dialog
session.start_dialog(dialog_id)       # 标记 dialog 为 active（select_dialog 时调）
async for evt in session.send_teacher_message(dialog_id, text):
    # evt: StudentStreamEvent (delta / final)
    ...                               # WS endpoint 把这个流转推给前端
session.mark_resolved(dialog_id, source)
session.abandon_dialog(dialog_id)
session.summary() -> dict             # 退出时给 summary 页
```

> **注意**：A 端可能在写 endpoint 时小幅调 `QASession` 接口（例如 `start_dialog` 幂等性、`send_teacher_message` 流式接口形态）。如有调整会单独 PR 通知你。

---

## 2. B 端在 M2 的全量任务清单

### 任务 #B0：~~Review 协议冻结 PR #77~~ ✅ 已完成

PR #77 已合入 main（squash commit `b53ef40`）。**协议已冻结**，可直接进入 #B1 / #B3。

后续协议变更须开 PR 改 `backend/schemas/ws_events.py` + `docs/api_contract.md §3` + A+B 双 approve（参见 §6 协作约定）。

**事后 review（可选）**：如果你看 schema 时发现还有缺字段或想加 `dialog_status_update` 这类便利事件，**请直接开 issue / 新 PR**，不要积压在脑里。

---

### 任务 #B1：后端 REST 路由（你领地：`backend/api/`）

#### 1.1 已存在的（M1 起骨架，B 端**需核实**）

```
POST /api/lessons/upload                    # 上传教案
GET  /api/lessons/{id}                      # 查询教案
GET  /api/lessons/{id}/recommended-personas # 拿默认推荐学生
GET  /api/personas?stage_id=...             # 列出人设
GET  /api/stages                            # 列出 6 个学段
GET  /health                                # 健康检查
```

源码在 `backend/api/lessons.py` / `personas.py` / `stages.py`。

#### 1.2 M2 新增（B 端**实现**）

```
POST /api/qa-sessions                  # 创建答疑 session
  Req:  { lesson_id: str, persona_ids: list[str], count_per_student?: int }
  Resp: { session_id: str, ws_url: str }

GET  /api/qa-sessions/{id}             # 查询 session 状态（可选，前端可不依赖）
  Resp: { session_id, lesson_id, status, students, dialogs_summary }

POST /api/qa-sessions/{id}/end         # 显式结束 session（也可由 WS close 隐式触发）
  Resp: { session_id, summary: {...} }
```

**实现建议**（A 配合）：

- 弄一个 `QASessionRegistry` 单例：`session_id -> QASession` 字典 + 异步锁
  - A 可以协助起个 `services/qa_session_registry.py`，要的话告诉我
- `POST /api/qa-sessions` 内部：
  1. 加载 lesson（已存在的 `LessonStore`）
  2. 加载 personas
  3. 构造 `QASession`，调 `await session.spawn(...)`
  4. 注册到 registry
  5. 返回 session_id + WS URL（如 `/ws/qa-sessions/{session_id}`）
- 失败处理：lesson_id 不存在 → 404；persona_ids 空或非法 → 400

#### 1.3 验收

- [ ] `uv run pytest tests/test_api_qa_sessions.py` 通过（你写的单元测试）
- [ ] `curl -X POST localhost:8000/api/qa-sessions -d '{"lesson_id":"...","persona_ids":["..."]}'` 返回 session_id

---

### 任务 #B2：SQLite 持久化（你领地：`backend/db/`，**M2 可推迟**）

`docs/proposal.md` / `docs/api_contract.md` 写过你需要做：

- `qa_sessions` 表
- `dialogs` 表
- `messages` 表

**M2 阶段建议**：**先不做**。`QASession` 已是内存态，summary 直接调 `summary()` 拿，不需 DB 落库。

留到 M3 跟评估 Agent 一起做（评估需要历史会话回看）。

---

### 任务 #B3：前端 WS 客户端 `frontend/lib/qa-ws.ts`

**前置**：#B0 通过（协议冻结）。

**目录建议**：

```
frontend/src/
├── lib/
│   ├── qa-ws.ts             # WS 客户端核心
│   └── qa-ws.types.ts       # TS 类型（照 docs/api_contract.md §3 抄）
└── hooks/
    └── useQASession.ts      # 与 Zustand store 集成
```

#### 3.1 类型定义（`qa-ws.types.ts`）

直接照 `docs/api_contract.md §3.3 / §3.4` 翻译成 TS。我已经把所有字段写得很 TS-friendly（受控字面量 + 可选字段标注）。

> 后续可以加 `pydantic-to-typescript` 自动同步，M2 阶段先手抄 ~150 行。

#### 3.2 客户端核心 API

```ts
// 推荐 API 形态（你按需调整）
export interface QAWsClient {
  on<T extends ServerMessage["type"]>(
    type: T,
    handler: (event: Extract<ServerMessage, { type: T }>) => void,
  ): () => void;  // 返回 unsubscribe
  send(msg: ClientMessage): void;
  close(): void;
  readonly status: "connecting" | "open" | "reconnecting" | "closed" | "replaced";
}

export function createQAWs(opts: {
  url: string;            // ws://localhost:8000/ws/qa-sessions/{id}
  onError?: (e: ErrorMessage) => void;
}): QAWsClient;
```

#### 3.3 必须实现的行为

- ✅ 自动重连：断线 3 秒后重试，最多 5 次；指数退避可选
- ✅ 收到 `error{code:"replaced"}` → **不要重连**（status 改 `replaced`）
- ✅ `seq` 单调校验：服务端帧 seq 跳号 → `console.warn`（先不 fail）
- ✅ 错误处理：JSON 解析失败 → console.error 但保持连接

#### 3.4 与 Zustand store 集成（`useQASession.ts`）

```ts
// store 关键 state
{
  sessionId: string | null,
  lesson: LessonMeta | null,
  students: WsStudentInfo[],
  dialogs: Map<string, DialogState>,  // dialog_id -> { status, replies, pending_red_dot }
  activeDialogId: string | null,
}

// 关键 mutations
- session_init  → 初始化 sessionId / lesson / students / dialogs
- dialog_active → activeDialogId = e.dialog_id
- reply_chunk   → dialogs.get(e.dialog_id).currentReply += e.delta
- reply_end     → 落地 reply 到 dialog.history，弹 self_resolved toast
- dialog_resolved / dialog_abandoned → 更新 dialog.status，红点-1
```

#### 3.5 验收

- [ ] mock WS 跑通完整链路（A 提供 mock server）
- [ ] 断线 3 秒后自动重连
- [ ] `vitest` 单元测试覆盖事件分发与重连

---

### 任务 #B4：Setup 流程 UI（教案 → 学段 → 学生）

**前置**：#B1（REST 已实现）。

#### 4.1 页面流（建议路由）

```
/                       # 首页 / 落地页（M2 简化版）
/setup                  # Step 1: 上传教案
/setup/personas         # Step 2: 推荐学生 + 调整
/qa/{session_id}        # Step 3: 1v1 答疑主界面（任务 #B5）
/qa/{session_id}/summary # Step 4: 退出总结（任务 #B6）
```

#### 4.2 Step 1：上传教案

- 拖拽上传或点选
- POST `/api/lessons/upload`（multipart）
- Loading 状态展示 LLM 抽取进度（≈ 5-15s）
- 成功后跳 Step 2，参数带 `lesson_id`

UI 元素：

- 大拖拽区域（shadcn Card）
- 解析中骨架屏
- 解析完展示 LessonMeta 卡片（subject / grade / topic / objectives / key_points）

#### 4.3 Step 2：学段 + 学生确认

- GET `/api/lessons/{id}/recommended-personas` 拿默认推荐
- 展示推荐学生卡片（avatar / name / subject_level / summary）
- 允许：
  - 改学段（下拉选 6 个学段）
  - 加学生（GET `/api/personas?stage_id=...` 列表里选）
  - 减学生（卡片右上角 X）
- 「开始陪练」按钮 → POST `/api/qa-sessions` → 跳 Step 3

---

### 任务 #B5：微信式 1v1 答疑 UI（**核心**）

**前置**：#B3 + #B4。

#### 5.1 视觉布局

```
┌─────────────────────────────────────┐
│ 教案信息条（顶部，可折叠）           │
├─────────────────────────────────────┤
│ ┌─学生列表─┐ ┌──对话窗口────────┐ │
│ │ 🔴 小红(3)│ │ 小红：老师，那个 │ │
│ │  小明 (2)│ │ ...               │ │
│ │ ✓ 小华   │ │ 你：……            │ │
│ │          │ │ 小红：哦，明白了！│ │
│ │          │ │ [输入框] [发送]    │ │
│ │          │ │ [已解答] [放弃]    │ │
│ └──────────┘ └────────────────────┘ │
└─────────────────────────────────────┘
```

#### 5.2 关键交互

| 行为 | 触发 | 视觉反馈 |
|---|---|---|
| 选中学生 | 点学生卡 | 发 `select_dialog` → 收 `dialog_active` → 右侧切窗口 |
| 切换学生 | 点另一个学生卡 | 当前对话保留进度（不发新事件，本地切窗口） |
| 师范生发言 | 输入回车 / 点发送 | 发 `teacher_message` → 收 `reply_chunk` 流式打字机 |
| 学生 [懂了] | `reply_end.self_resolved=true` | 弹 toast「小红表示懂了，标记为已解答吗？」 |
| 标记已解答 | toast 确认 / 手动点按钮 | 发 `resolve` → 收 `dialog_resolved` → 红点 -1 / 卡片变 ✓ |
| 放弃对话 | 点「放弃」 | 发 `abandon` → 收 `dialog_abandoned` → 卡片变灰 |
| 全部解答完 | 所有 dialog 都 ended | 「结束陪练」按钮亮起 → 跳 summary |

#### 5.3 状态图标约定

| 图标 | 含义 |
|---|---|
| 🔴 N | N 个未解答问题（红点带数） |
| · (浅色 dot) | 进行中或已选中 |
| ✓ | 全部解答完毕 |
| ✗ (灰色) | 已放弃 |

#### 5.4 流式打字机效果

- 收到 `reply_chunk.delta` 直接 append 到 dialog.currentReply
- 不要等 `reply_end` 才显示 — 那就失去流式价值了
- `reply_end` 到达时用 `full_content` 校正（防止前端拼接边界 bug）
- 流式期间禁用「发送」按钮（不允许并发 teacher_message）

#### 5.5 验收

- [ ] 上传教案 → 看到 N 个学生待解答问题（红点显示数量）
- [ ] 点击某学生进入 1v1 对话；学生回复有打字机效果
- [ ] 切换到另一个学生再切回来，原对话进度不丢
- [ ] `[懂了]` 标记弹确认 toast；确认后红点 -1 卡片变 ✓
- [ ] 全部解答完后点「结束陪练」看到 summary 页
- [ ] 视觉风格与现有 setup 流程统一

---

### 任务 #B6：退出 summary 页

**前置**：#B5。

调 `summary` 事件返回的 data（A 端在 WS 关闭前会推一次）：

```python
# QASession.summary() 返回 dict 形如：
{
  "session_id": "...",
  "lesson": {...},
  "total_questions": 6,
  "resolved": 4,
  "abandoned": 1,
  "pending": 1,
  "covered_key_points": ["理解几分之一", "..."],
  "broken_misconception_ids": ["math_fraction_01", "..."],
  "resolution_sources": {"teacher_marked": 2, "self_resolve": 2},
  "students_breakdown": [
    {"id": "p1", "name": "小红", "resolved": 2, "abandoned": 0, "pending": 1},
    ...
  ]
}
```

UI 元素：

- 顶部大数字：解答 X / 放弃 Y / 总数 Z
- 教学重点覆盖列表（基于 `covered_key_points`）
- 破除迷思列表（基于 `broken_misconception_ids`，可能要根据 id 反查 `data/misconceptions/` 拿迷思 name 展示）
- 学生维度柱状图 / 进度条
- 「再来一次」按钮 → 回 setup
- 「导出报告」按钮（M3 再做，先灰掉）

---

### 任务 #B7：视觉打磨（最后做）

- TailwindCSS + shadcn/ui 主题统一
- 颜色：建议主色 `#3b82f6` (blue-500) + 强调色 `#10b981` (emerald-500)
- 字体：思源黑体 / 默认 system-ui
- 动效：dialog 切换淡入；新 reply_chunk 抖动一下学生头像；summary 大数字滚动
- 移动端响应式：M2 不要求

---

## 3. 推进顺序

以 PR 为粒度，按依赖关系串行 / 并行。

### 阶段 1：协议冻结 ✅ 已完成

- PR #77（A）— `schemas/ws_events.py` + `docs/api_contract.md §3`
- PR #78（C）— 转型清理（persona v1.1 + 文档对齐）

### 阶段 2：后端与前端骨架（并行）

**B 端**（你）：

1. **B1** 写 REST 路由：`POST /api/qa-sessions` 等 → 提 PR `closes #72 部分`
2. **B3** 起 `frontend/lib/qa-ws.ts` 类型定义 + 客户端骨架，联 mock WS 跳起来

**A 端**：

1. 写 `backend/api/qa_ws.py`（分支 `feat/qa-ws-endpoint`）→ 提 PR `refs #71`
2. 写 `backend/scripts/mock_ws_server.py` 给 B 用（同 PR 或单独 PR）

### 阶段 3：联调

- B 的 ws-client 从 mock 切到真后端
- bug 互修：JSON 字段名不对 / seq 跳号 / 流式拼接 bug 等
- **任意一方提 e2e 验证 PR**（`wscat` 脚本或 Playwright）→ `closes #71` ✅

### 阶段 4：B 端 UI 主体

1. **B4** Setup 流程 UI（教案上传 → 学生确认 → 进入陪练）
2. **B5** 微信式 1v1 答疑 UI（带多学生切换 + 流式打字机）
3. **B6** 退出 summary 页
4. **B7** 视觉打磨

最后一个 UI PR → `closes #72` ✅

### #71 拆分总览

| 顺序 | PR | Owner | 关联 |
|---|---|---|---|
| 1 | #77 协议冻结 | A | refs #71 ✔ 已合 |
| 2 | `feat/qa-ws-endpoint` | A | refs #71 |
| 3 | `feat/qa-ws-client` | B | refs #71 |
| 4 | e2e 验证 | A 或 B | `closes #71` ✅ |

#72 由 B 端多个 UI PR 逐步推进，最后一个 `closes #72`。

---

## 4. 接口边界清单（A↔B 黄线）

### 4.1 A 端 M1 代写的 B 领地（B 端 M2 起完全接管）

M1 期间因接口与后端业务逻辑紧耦合（`lessons.py` 直接调 `rag.parser` / `rag.indexer`；`personas.py` / `stages.py` 直接 load JSON 数据），A 端**代写**了下列原属 B 领地的文件：

| 文件 | 来源 PR | 状态 |
|---|---|---|
| `backend/api/lessons.py` | #53 #60 #64 | 已上线，提供 upload / get / recommended-personas |
| `backend/api/personas.py` | #59 #60 | 已上线，提供 list / detail |
| `backend/api/stages.py` | #59 #60 | 已上线，提供 list / detail |
| `backend/api/response.py` | #60 | 统一 ApiResponse envelope |

**M2 起 B 端对这些文件有完全所有权**：可以自由重构、改字段、改路由、改返回 schema。

**A 端默认不再主动改这些文件**，除非：

- B 显式委托
- 紧急 bug fix（事后必须在 PR / issue 告知 B）
- 协议性变更（如 ApiResponse envelope 调整），需 A+B 双 approve

### 4.2 A 端会碰的 B 领地（M2 期间，已有 #71 issue 授权）

| 文件 | 由谁实现 | 备注 |
|---|---|---|
| `backend/api/qa_ws.py` | A | WS endpoint，#71 明文授权；B review |
| `backend/api/qa_sessions.py` | B（如需 A 协助起骨架请告知） | M2 新增 REST：POST /api/qa-sessions 等 |

### 4.3 A 完全不碰的 B 领地

- `frontend/` —— **完全**不碰
- `backend/db/` —— M3 再说，M2 暂不需要

### 4.4 B 完全不碰的 A 领地

- `backend/agents/` / `services/` / `rag/` / `llm/` / `prompts/`
- `data/` 下文件（除非 C 委托）

### 4.5 B 可读但不写的 A 领地（M2 期间频繁参考）

| 路径 | 用途 |
|---|---|
| `backend/schemas/*.py` | 写 TS 类型时对照 |
| `backend/schemas/ws_events.py` | **WS 协议权威 schema** |
| `backend/services/qa_session.py` | 写 REST 时调用 |
| `backend/agents/student.py` | 理解流式行为 |

> **协议性 schema**（`schemas/ws_events.py` / `docs/api_contract.md §3`）虽属 A 领地，但**任何变更都需 A+B 双 approve**。这是 #71 issue 协议冻结的核心约定。

---

## 5. 风险与坑

### 5.1 流式 chunk 拼接 vs `full_content` 不一致

**场景**：A 端 hold-back 缓冲在末尾留 16 字符，所以 `reply_end.full_content` 末尾可能比已 emit delta 多一段。

**协议保证**：A 在 `reply_end` 之前会**补发一个 delta** 把剩余 holdback 内容推完。所以前端拼接的 `currentReply` 在 `reply_end` 到达时**已等于 full_content**。

**但**：建议前端仍用 `full_content` 校正一次，防止网络分片边界 bug。

### 5.2 单 session 单连接

新连接挤旧的 → 旧连接收到 `error{code:"replaced"}` + 关闭码 1000。

**前端坑**：HMR 热更或 React Strict Mode 双挂载会触发两次连接，导致互相挤掉。开发环境可以加：

```ts
if (process.env.NODE_ENV === "development") {
  // 第一次挂载就连，HMR 时 useEffect cleanup 显式 close
}
```

### 5.3 教案上传慢

LLM 抽取 LessonMeta 要 5-15 秒。上传时给个长 loading + 进度提示，**不要让用户以为卡死**。

### 5.4 切换学生时停止流式

如果某 dialog A 正在流式输出，用户切到 dialog B：

- **A 实现**：流不会中断，A 端继续把剩余 chunk 推完（带 dialog_id），B 端 store 累加到 A dialog 的状态里
- **前端**：只渲染 activeDialogId 的内容，其他 dialog 的 chunk 默默累积在 store 里
- **切回 A 时**：直接显示已累积的 currentReply

---

## 6. 联系方式 & 协作约定

- 协议变更：开 PR 改 `schemas/ws_events.py` + `docs/api_contract.md` + 双 approve
- 接口形态调整：直接在 issue / PR 评论留言，必要时 GitHub mention `@Nekooo915`
- 阻塞性问题：在对应 issue 留 comment + assign 给 A
- 紧急同步：直接微信 / 项目群

---

## 7. 文档索引

| 文档 | 用途 | 最近更新 |
|---|---|---|
| [`docs/api_contract.md`](./api_contract.md) | REST + WS 协议规范（权威） | #77（v1 §3 替换） |
| [`docs/roles.md`](./roles.md) | 三人分工与领地细则 | #78 |
| [`docs/persona_design.md`](./persona_design.md) | 学生人设建模 | #78 |
| [`docs/proposal.md`](./proposal.md) | 立项书（已对齐 1v1 答疑陪练定位） | #78 |
| [`docs/setup_macos_linux.md`](./setup_macos_linux.md) | mac/linux 部署 | #76 |
| [`docs/setup_windows.md`](./setup_windows.md) | windows 部署 | #76 |
| [`README.md`](../README.md) | 项目主页（已对齐 1v1 定位） | #78 |
| [`backend/README.md`](../backend/README.md) | 后端速查 | — |
| [`backend/schemas/ws_events.py`](../backend/schemas/ws_events.py) | **WS 协议权威 schema** | #77 |
| [`backend/schemas/student.py`](../backend/schemas/student.py) | Persona v1.1（14 字段） | #78 |
| [`backend/services/qa_session.py`](../backend/services/qa_session.py) | QASession 业务编排 | #74 |
| [`data/personas/_schema.json`](../data/personas/_schema.json) | Persona JSON Schema v1.1 | #78 |

---

## 8. Checklist（B 端打勾用）

- [x] #B0 ~~Review PR #77~~ ✅ 已合入 main
- [ ] #B1 实现 `POST /api/qa-sessions` 等 REST
- [ ] #B3 实现 `frontend/lib/qa-ws.ts` + 类型定义
- [ ] #B4 Setup 流程 UI（教案 → 学生）
- [ ] #B5 微信式 1v1 答疑 UI
- [ ] #B6 退出 summary 页
- [ ] #B7 视觉打磨
- [ ] (可选) #B2 SQLite 持久化（建议推迟到 M3）

完成后在 #72 issue 里勾验收清单 + 提总 PR。

---

**有问题随时丢消息或 GitHub mention，A 端会优先解锁你的阻塞。祝顺利。**

— A-Agent
