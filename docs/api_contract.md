# EchoClass API 合约 · v0 (draft)

> **状态**：Draft · 由 Cascade 基于架构方案生成的初稿
> **维护者**：B-Full（主）、A-Agent（协同）
> **变更流程**：修改须开 PR，A 和 B 都 approve 后合并
> **关联 Issue**：#21 [W1-08]

---

## 0. 通用约定

### 0.1 基础 URL

| 环境 | URL |
|---|---|
| 本地 | `http://localhost:8000` |
| 前端环境变量 | `NEXT_PUBLIC_API_BASE` |

### 0.2 通用响应包装

所有 REST 接口使用统一响应结构：

```ts
interface ApiResponse<T> {
  code: number;        // 0 = 成功；非 0 = 业务错误
  message: string;     // 错误描述（成功时为 "ok"）
  data: T | null;      // 业务数据
  request_id: string;  // 服务端生成，用于排查
}
```

### 0.3 错误码

| code | 含义 | HTTP |
|---|---|---|
| `0` | 成功 | 200 |
| `40001` | 参数校验失败 | 400 |
| `40401` | 资源不存在 | 404 |
| `42901` | 超出配额 / 频率限制 | 429 |
| `50001` | 内部错误 | 500 |
| `50002` | LLM 上游错误 | 502 |

### 0.4 数据类型别名

```ts
type UUID = string;          // e.g. "01J8..."
type ISO8601 = string;       // e.g. "2026-04-22T10:00:00Z"
type Grade = "P1"|"P2"|"P3"|"P4"|"P5"|"P6"|"J1"|"J2"|"J3"|"H1"|"H2"|"H3";
type Subject = "math" | "chinese" | "english" | "physics" | "chemistry" | "biology";
```

### 0.5 鉴权（M3 起生效）

> **状态**：v2 / M3 协议冻结 · 关联 Epic #121
> **后端实现**：`backend/api/auth.py`（B 端） · 依赖注入：`get_current_user`
> **影响范围**：`/api/lessons/*`、`/api/qa-sessions/*`、`/ws/qa-sessions/*` 全部需要鉴权

#### 0.5.1 登录与 Token

- **`POST /api/auth/register`**：body `{username, password}` → `ApiResponse<{user_id}>`
- **`POST /api/auth/login`**：body `{username, password}` → `ApiResponse<{access_token, token_type:"Bearer"}>`
- **Token 形式**：JWT（HS256），claims 至少含 `sub`(user_id) / `username` / `iat` / `exp`
- **M3 最小化**：**只发 access token**，不发 refresh token；过期即重新登录。比赛后再扩展

#### 0.5.2 REST 请求携带 Token

- **Header**：`Authorization: Bearer <jwt>`
- 所有受保护端点未携带或 token 无效 → HTTP `401`，错误码 `40101`
- 已登录但无权限访问他人资源 → HTTP `403`，错误码 `40301`

#### 0.5.3 `owner_id` 语义

- **任何 REST body 都不接受 `owner_id` 字段**；后端从 JWT claim 取
- 例如 `POST /api/qa-sessions` 的请求体**不变**，但 session 创建后自动绑定当前用户
- `GET /api/qa-sessions` 默认只返回当前用户的 session

#### 0.5.4 WebSocket 鉴权

- WS 不支持自定义 header；token 走 query string：
  `ws://host:port/ws/qa-sessions/{session_id}?token=<jwt>`
- 握手阶段校验；失败以 close code `4401` 关闭，不发 `error` 帧
- **安全提醒**：生产部署务必用 `wss://`，避免 token 明文泄露

#### 0.5.5 错误码补充

| code | 含义 | HTTP |
|---|---|---|
| `40101` | 未登录 / token 无效或过期 | 401 |
| `40301` | 已登录但无权访问该资源 | 403 |

---

## 1. 教案 Lessons

### 1.1 上传教案

**`POST /api/lessons/upload`** — multipart/form-data

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | File | ✅ | PDF / Markdown / TXT，≤ 10MB |
| `title` | string | ❌ | 用户自定义标题，缺省从文件解析 |

**响应** `data`：

```ts
interface LessonUploadResp {
  lesson_id: UUID;
  subject: Subject;
  grade: Grade;
  topic: string;                    // 课题，e.g. "分数的初步认识"
  objectives: string[];             // 教学目标
  key_points: string[];             // 重点
  difficult_points: string[];       // 难点
}
```

### 1.2 查询教案

**`GET /api/lessons/{lesson_id}`**

**响应** `data`：

```ts
interface LessonRecord {
  lesson_id: UUID;
  filename: string;
  meta: Record<string, unknown>;
  text_length: number;
  chunk_count: number;
}
```

### 1.3 列出教案

**`GET /api/lessons?limit=20&cursor=<opaque>`**

```ts
interface LessonListResp {
  items: LessonListItem[];
  next_cursor: string | null;
}
interface LessonListItem {
  lesson_id: UUID;
  title: string;
  subject: Subject;
  grade: Grade;
  created_at: ISO8601;
}
```

---

## 2. 会话 Sessions

> **状态**：Draft / 规划中（接口与字段仍待实现，不作为前端稳定接入依据）

### 2.1 创建会话（开课）

**`POST /api/sessions`**

```ts
interface CreateSessionReq {
  lesson_id: UUID;
  class_profile: ClassProfile;
}

interface ClassProfile {
  student_count: number;                  // 3-8
  activity: "low" | "mid" | "high";       // 活跃度
  discipline: "loose" | "mid" | "strict"; // 纪律性
  persona_ids?: UUID[];                   // 指定人设；缺省则系统自动挑选
}
```

**响应** `data`：

```ts
interface CreateSessionResp {
  session_id: UUID;
  lesson_id: UUID;
  students: StudentInfo[];
  ws_url: string;                   // 带鉴权 token 的 WebSocket URL
  started_at: ISO8601;
}

interface StudentInfo {
  speaker_id: string;               // 会话内稳定 ID，e.g. "stu_01"
  persona_id: UUID;
  name: string;
  avatar_url: string;
  seat: number;                     // 座位号 0..N-1
  personality_tags: string[];
}
```

### 2.2 结束会话

**`POST /api/sessions/{session_id}/end`**

**响应** `data`：

```ts
interface EndSessionResp {
  session_id: UUID;
  ended_at: ISO8601;
  report_url: string;               // 前端路由，e.g. "/sessions/:id/report"
  report_ready: boolean;            // 评估是否已生成完；false 时需轮询 2.4
}
```

### 2.3 获取会话详情

**`GET /api/sessions/{session_id}`**

```ts
interface SessionDetail {
  session_id: UUID;
  lesson_id: UUID;
  status: "active" | "ended" | "evaluating";
  students: StudentInfo[];
  started_at: ISO8601;
  ended_at: ISO8601 | null;
  message_count: number;
}
```

### 2.4 获取诊断报告

**`GET /api/sessions/{session_id}/report`**

```ts
interface TeachingReport {
  session_id: UUID;
  generated_at: ISO8601;
  overall_score: number;            // 0-100
  dimensions: {
    lesson_design: DimensionScore;      // 教学设计
    interaction: DimensionScore;        // 课堂互动
    expression: DimensionScore;         // 语言表达
    management: DimensionScore;         // 课堂管理
  };
  metrics: RuleMetrics;
  highlights: Highlight[];          // 关键时刻 / 改进机会
  suggestions: Suggestion[];        // 改进建议
}

interface DimensionScore {
  score: number;                    // 0-100
  sub_items: { name: string; score: number; comment: string; }[];
  summary: string;
}

interface RuleMetrics {
  teacher_talk_ratio: number;       // 0-1
  open_question_ratio: number;      // 开放 vs 封闭提问
  avg_wait_time_ms: number;         // 候答时间中位数
  unresponded_student_questions: number;
  interaction_matrix: number[][];   // Flanders 互动分析 10x10
}

interface Highlight {
  timestamp_ms: number;             // 相对会话开始的毫秒
  type: "missed_misconception" | "good_question" | "short_wait_time" | "off_topic_unhandled";
  excerpt: string;                  // 相关片段
  comment: string;                  // LLM 点评
}

interface Suggestion {
  title: string;
  problem: string;
  reason: string;
  actionable_tip: string;
  related_highlights: number[];     // 指向 highlights 数组索引
}
```

### 2.5 答疑陪练 QA Sessions（1v1 pivot 后实际实现）

> **状态**：v1（M2） · 关联 Issue #72 / #B1
> **后端实现**：`backend/api/qa_sessions.py`（B 端） · 模型：`backend/schemas/qa_session_api.py`
> **关系**：M1 答疑陪练 pivot (#74) 后，§2.1-2.4 多学生课堂接口暂搁置；本节是
> **真正在跑** 的 REST 接口。WebSocket 部分见 §3。

#### 2.5.1 创建答疑 session

**`POST /api/qa-sessions`**

```ts
interface CreateQASessionReq {
  lesson_id: string;             // 取自 POST /api/lessons/upload 的返回
  persona_ids: string[];         // 至少 1 个；可重复传同一 id（自动去重）
  count_per_student?: number;    // 1-8，默认 3。决定每个学生 spawn 多少个问题
}

interface CreateQASessionResp {
  session_id: string;
  ws_url: string;                // "/ws/qa-sessions/{session_id}"
  lesson: LessonMeta;            // 与教案上传时一致
  students: WsStudentInfo[];     // 与 §3.4 同形
  questions: StudentQuestion[];  // spawn 出的问题队列；与 WS 首帧 questions 一致
}
```

**错误**：

- `404` `lesson_id` 不存在
- `400` `persona_ids` 中任一 id 不存在
- `422` body schema 错误（`persona_ids` 空 / `count_per_student` 越界）
- `500` 学生 agent 构造或 spawn 失败 / 未生成任何问题

**语义**：

- 服务端会按 `persona_ids` 构造 `StudentAgent`，并行让每个学生
  `generate_questions(lesson_meta, count=count_per_student)`，结果按"轮询交叉"
  策略入队（学生间穿插，相邻问题倾向不同学生）
- 创建成功即注册到进程级 `QASessionRegistry`；前端拿到 `ws_url` 后即可建 WS

#### 2.5.2 查询 session 现状

**`GET /api/qa-sessions/{session_id}`**

```ts
interface QASessionStateResp {
  session_id: string;
  lesson: LessonMeta;
  students: WsStudentInfo[];
  dialogs: DialogStateSummary[];
  pending: number;
  active: number;
  resolved: number;
  abandoned: number;
}

interface DialogStateSummary {
  id: string;                                     // M2 = question.id；M3 = student_id
  student_id: string;
  student_name: string;
  status: "pending" | "active" | "resolved" | "abandoned";
  question_preview: string;                       // 问题正文前 80 字符（M3 = 首问预览）
  turn_count: number;                             // 一来一回算一轮
  resolution_source?:
    | "self_resolve"
    | "teacher_marked"
    | "auto_evaluator"
    | "abandoned"
    | "turn_limit";              // M3：单题累计 turn 数超上限被自动作废
  history: DialogMessage[];                       // 完整对话历史（issue #102）
}

interface DialogMessage {
  role: "teacher" | "student";
  content: string;
  timestamp: string;                              // ISO-8601
  self_resolved: boolean;                         // 仅 student 回合可能 true
  is_new_question: boolean;                       // M3：由 QASession 从 asked_questions 队列确定性弹出的新问题为 true；M2 永远 false
  question_id?: string | null;                    // M3：本条所属 question id；M2 永远 null
}
```

> ⚠️ **形态说明**（issue #111）：
>
> - **M2 闯关模式**（v1，已上线）：一题一 dialog，``id == question.id``，``history`` 全部属于同一道题
> - **M3 连续答疑模式**（v2，当前实现）：一学生一 dialog，``id == student_id``，``history`` 可能跨越多个 question（确定性队列弹出的新问题回合 ``is_new_question=true``）
>
> 两种形态在字段层兼容：``is_new_question`` / ``question_id`` 为M3 新增字段，M2 永远默认值。

**错误**：`404` session 不存在。

**语义**：刷新陪练页 / summary 页查询用；主动事件推送仍走 WS（§3）。
M2 进程内 registry，进程重启即丢；M3 持久化后会从 SQLite 兜底。

`history` 字段（issue #102）支持页面级导航后复原对话进度：前端在
`useQASession` 挂载时 GET 一次即可 seed 整个 reducer，再正常走 WS 增量。
未发生过对话的 dialog 为空数组。

#### 2.5.3 显式结束 session

**`POST /api/qa-sessions/{session_id}/end`**

```ts
interface QASessionEndResp {
  session_id: string;
  summary: {
    session_id: string;
    lesson_topic: string;
    total_questions: number;
    resolved: number;
    abandoned: number;
    pending: number;
    active: number;
    covered_key_points: string[];
    broken_misconception_ids: string[];
    resolution_sources: { [source: string]: number };
  };
}
```

**错误**：`404` session 不存在（包含已结束过一次的场景，幂等保护）。

**语义**：

- 从 registry 移除 session，返回 `QASession.summary()` 快照
- **不主动关闭已建立的 WebSocket**；前端在收到 200 后应自行 `client.close()`
- 二次调用同 session_id 必然 404，前端应据此判定"是否已经结束过"

### 2.6 评估报告 Evaluation（M3 起生效）

> **状态**：v2 / M3 协议冻结 · 关联 Epic #121 · 依赖 Rubric v0 #M3-0-Rubric
> **后端产出**：EvaluatorAgent（#M3-A3）+ FeedbackAgent（#M3-A4）
> **API 实现**：B 端 #M3-B3
> **持久化**：`evaluations` + `feedbacks` 表（#M3-B2）

session 结束后（`POST /api/qa-sessions/{id}/end` 或 WS `summary`），后端**异步**触发
EvaluatorAgent + FeedbackAgent。前端通过 REST 轮询获取结果，**不走 WebSocket**（避免
把异步任务复杂度塞进 WS）。

#### 2.6.1 查询评估结果

**`GET /api/qa-sessions/{session_id}/evaluation`**

鉴权：Bearer JWT（§0.5.2）。仅 session owner 可访问，否则 `403 / 40301`。

**响应状态机**：

| HTTP | 场景 | `data` |
|---|---|---|
| 200 | 评估完成 | `{evaluation: EvaluationReport, feedback: TeacherFeedback}` |
| 202 | 评估进行中（session 刚结束，Agent 还没跑完） | `{status: "pending"}` |
| 404 | session 不存在 / session 未结束 / 评估生成失败且无降级结果 | — |
| 401 | 未登录 | — |
| 403 | 登录了但非 owner | — |

**前端约定**：session 结束后以 **2 秒间隔轮询**；最长 **60 秒超时**，超时后展示"评估暂不可用"+ 重试按钮。

#### 2.6.2 EvaluationReport

```ts
interface Evidence {
  dialog_id: string;           // == student_id
  chunk_seq?: number | null;   // 可选：证据出现在第几轮 reply
  excerpt: string;             // 原文摘录，≤ 120 字
}

interface RubricScore {
  dimension: string;           // e.g. "questioning_guidance" / "concept_accuracy"
  score: number;               // 0–4 整数，与 Rubric v0 对齐
  rationale: string;           // 打分理由（≤ 200 字）
  evidence: Evidence[];        // 支撑片段，可空
}

interface EvaluationReport {
  session_id: UUID;
  rubric_version: string;      // e.g. "v0"；与 data/rubrics/{version}.json 对应
  scores: RubricScore[];       // 每个维度一条
  overall: number | "unavailable";  // 汇总分（0–4 浮点）；LLM 失败时降级为 "unavailable"
  generated_at: ISO8601;
}
```

#### 2.6.3 TeacherFeedback

```ts
interface TeacherFeedback {
  strengths: string[];         // 做得好的地方，≥ 1 条
  improvements: string[];      // 具体可改进点，≥ 1 条
  next_steps: string[];        // 下一步练习建议，≥ 1 条
  tone: "encouraging" | "neutral" | "critical";
  generated_at: ISO8601;
}
```

#### 2.6.4 不变式

- **每个 session 最多一份 `EvaluationReport`**：DB 层 `evaluations.session_id UNIQUE`
- **降级策略**：LLM 失败时 `overall="unavailable"`，`scores` 保留已成功的维度（允许空）；`TeacherFeedback` 可为占位文案但字段不为 null
- **Rubric 演进**：`rubric_version` 与 `data/rubrics/{v}.json` 绑定；未来 v1 上线后不追溯重算已有 session
- **前端反解析**：遇到未知 `dimension` 或 `tone` 应静默忽略不报错（向前兼容）

#### 2.6.5 Pydantic 模型对照

权威来源：`backend/schemas/evaluation.py`（#M3-A1） / `backend/schemas/feedback.py`（#M3-A2）

---

## 3. WebSocket `/ws/qa-sessions/{session_id}` — 1v1 答疑陪练

> **状态**：v1（M2 冻结） · 关联 Issue #71
> **后端实现**：`backend/api/qa_ws.py`（A 端） · 协议模型：`backend/schemas/ws_events.py`（A 端）
> **前端实现**：`frontend/lib/qa-ws.ts`（B 端）
> **变更流程**：协议字段、type 枚举、错误码任一改动须开 PR 修改本节 + `schemas/ws_events.py`，A + B 双 approve 后方可合入

> ⚠️ **历史遗留**：早期设计的"多学生并发课堂"WebSocket 协议（含 `director_event` / `board_update` / 多 reply 并发）已废弃。M1 答疑陪练 pivot (#74) 后改为 1v1 串行模型，仅保留下文协议。

### 3.1 连接

- **URL**：`ws://localhost:8000/ws/qa-sessions/{session_id}`
- **协议**：文本帧，**每帧一条 JSON**（JSON Lines）
- **心跳**：M2 暂不实现 ping/pong；30 秒空闲不视为异常。后续如需要再扩展
- **单 session 单连接**：第二次连同一 `session_id` 时，旧连接收到 `{"type":"error","code":"replaced"}` 并被服务端关闭（关闭码 `1000`）
- **关闭码**：
  - `1000` 正常关闭（含被新连接挤掉）
  - `4004` `session_id` 不存在
  - `4009` session 已结束（已发过 `summary` 后再连）
  - `4401` 鉴权失败：`?token=` 缺失 / 无效 / 过期（M3 起生效，详见 §0.5.4）

### 3.2 通用约定

- **服务端 → 客户端** 每帧带单调递增的 `seq: number`（从 0 起，连接生命周期内唯一），客户端可据此检测乱序 / 丢帧
- **客户端 → 服务端** 每帧可带可选 `timestamp: ISO8601`（便于排错），服务端不做强校验
- 嵌入对象（`LessonMeta` / `StudentQuestion`）直接复用业务 schema，与 REST 接口一致；前端按需取字段

### 3.3 客户端 → 服务端

```ts
type ClientMessage =
  | SelectDialog
  | TeacherMessage
  | Resolve
  | Abandon;

interface SelectDialog {
  type: "select_dialog";
  dialog_id: string;                // == StudentQuestion.id
  timestamp?: ISO8601;
}

interface TeacherMessage {
  type: "teacher_message";
  dialog_id: string;
  text: string;                     // 师范生本轮发言；非空
  timestamp?: ISO8601;
}

interface Resolve {
  type: "resolve";
  dialog_id: string;
  source?: "teacher_marked" | "self_resolve";  // 默认 "teacher_marked"
  timestamp?: ISO8601;
}

interface Abandon {
  type: "abandon";
  dialog_id: string;
  timestamp?: ISO8601;
}
```

**语义**：

- `select_dialog`：从队列里挑一个学生进入 1v1 对话；幂等（已 active 时无副作用）
- `teacher_message`：师范生在某个 active dialog 内发言；服务端响应若干 `reply_chunk` + 一个 `reply_end`。若 dialog 处于 `pending` 服务端会自动 `start_dialog` 后再处理
- `resolve`：标记 dialog 为已解答。`source` 区分是师范生主动点确认（`teacher_marked`）还是承认学生 `[懂了]` 自我宣称（`self_resolve`）
- `abandon`：放弃 dialog；转 `abandoned` 状态后不再可继续

### 3.4 服务端 → 客户端

```ts
type ServerMessage =
  | SessionInit
  | DialogActive
  | ReplyChunk
  | ReplyEnd
  | StudentNewQuestion        // 仅 M3 连续答疑模式出现
  | DialogResolved
  | DialogAbandoned
  | Summary
  | ErrorMessage;

interface SessionInit {
  type: "session_init";
  seq: number;                      // 通常 0
  timestamp: ISO8601;
  session_id: string;
  lesson: LessonMeta;               // 直接复用 §1 LessonMeta
  students: WsStudentInfo[];        // 本场参与的学生
  questions: StudentQuestion[];     // 学生主动构思好的问题队列；与 next_pending 顺序一致
}

interface WsStudentInfo {
  id: string;
  name: string;
  stage_id: string;
  subject_level: string;            // "优秀" | "中等" | "薄弱"
  avatar_seed: string;
  summary: string;                  // 一句话概括
}

interface DialogActive {
  type: "dialog_active";
  seq: number;
  timestamp: ISO8601;
  dialog_id: string;
}

interface ReplyChunk {
  type: "reply_chunk";
  seq: number;                      // 全连接单调递增
  timestamp: ISO8601;
  dialog_id: string;
  delta: string;                    // 增量文本（不含 [懂了] 标记）
  chunk_seq: number;                // 同 dialog 内单调递增，从 0 起
}

interface ReplyEnd {
  type: "reply_end";
  seq: number;
  timestamp: ISO8601;
  dialog_id: string;
  full_content: string;             // 完整回复（已剥离标记，权威文本）
  self_resolved: boolean;           // LLM 是否在末尾打了 [懂了]
}

// 仅 M3 连续答疑模式（issue #111）出现；M2 服务端不发出。
// 老前端遇到未知类型应静默丢弃不报错。
interface StudentNewQuestion {
  type: "student_new_question";
  seq: number;
  timestamp: ISO8601;
  dialog_id: string;                // M3 下 == student_id
  question: StudentQuestion;        // 复用 §1 StudentQuestion
  after_reply_chunk_seq?: number | null;  // 可选：在哪轮末产生；前端可忽略
}

interface DialogResolved {
  type: "dialog_resolved";
  seq: number;
  timestamp: ISO8601;
  dialog_id: string;
  source: "teacher_marked" | "self_resolve" | "turn_limit" | "auto_evaluator" | "abandoned";
}

interface DialogAbandoned {
  type: "dialog_abandoned";
  seq: number;
  timestamp: ISO8601;
  dialog_id: string;
}

interface Summary {
  type: "summary";
  seq: number;
  timestamp: ISO8601;
  data: Record<string, unknown>;    // QASession.summary() 返回结构
}

interface ErrorMessage {
  type: "error";
  seq: number;
  timestamp: ISO8601;
  code: WsErrorCode;
  message: string;
  dialog_id?: string;
}

type WsErrorCode =
  | "dialog_not_found"
  | "dialog_already_ended"
  | "session_not_found"
  | "invalid_message"
  | "replaced"
  | "llm_failed"
  | "internal_error";
```

### 3.5 典型消息序列

#### 3.5.1 M2 闯关模式（v1，一题一 dialog）

```
Server → Client: {"type":"session_init","seq":0,"session_id":"sess-1","lesson":{...},"students":[...],"questions":[...]}
Client → Server: {"type":"select_dialog","dialog_id":"q-1"}
Server → Client: {"type":"dialog_active","seq":1,"dialog_id":"q-1"}
Client → Server: {"type":"teacher_message","dialog_id":"q-1","text":"你说说看你是怎么想的？"}
Server → Client: {"type":"reply_chunk","seq":2,"dialog_id":"q-1","delta":"嗯……","chunk_seq":0}
Server → Client: {"type":"reply_chunk","seq":3,"dialog_id":"q-1","delta":"我觉得分母","chunk_seq":1}
Server → Client: {"type":"reply_chunk","seq":4,"dialog_id":"q-1","delta":"是下面那个数？","chunk_seq":2}
Server → Client: {"type":"reply_end","seq":5,"dialog_id":"q-1","full_content":"嗯……我觉得分母是下面那个数？","self_resolved":false}
Client → Server: {"type":"teacher_message","dialog_id":"q-1","text":"对的！分母代表分成几份。"}
Server → Client: {"type":"reply_chunk","seq":6,"dialog_id":"q-1","delta":"哦！我懂了。","chunk_seq":0}
Server → Client: {"type":"reply_end","seq":7,"dialog_id":"q-1","full_content":"哦！我懂了。","self_resolved":true}
Client → Server: {"type":"resolve","dialog_id":"q-1","source":"self_resolve"}
Server → Client: {"type":"dialog_resolved","seq":8,"dialog_id":"q-1","source":"self_resolve"}
```

#### 3.5.2 M3 连续答疑模式（v2，一学生一 dialog，issue #111）

引入 ``student_new_question`` 帧后的泛型序列（``stu_a`` = 某学生 thread id）。
**关键机制**：每个学生 spawn 时预生成 N 道题（当前 N=3），按确定性队列推进，
不再调用 LLM 决定是否追问。推进触发条件：学生 ``self_resolved=true`` 或当前题
累计 turn 数达到上限 M（当前 M=8）。

```
Server → Client: {"type":"session_init","seq":0,...,"questions":[Q1_for_a, Q1_for_b]}  // 每人首问
Client → Server: {"type":"select_dialog","dialog_id":"stu_a"}
Server → Client: {"type":"dialog_active","seq":1,"dialog_id":"stu_a"}
Client → Server: {"type":"teacher_message","dialog_id":"stu_a","text":"说说看"}
Server → Client: {"type":"reply_chunk","seq":2,...,"chunk_seq":0}
Server → Client: {"type":"reply_end","seq":3,"dialog_id":"stu_a","full_content":"...","self_resolved":false}
Client → Server: {"type":"teacher_message","dialog_id":"stu_a","text":"对的！分母代表分成几份。"}
Server → Client: {"type":"reply_chunk","seq":4,...,"chunk_seq":0}
Server → Client: {"type":"reply_end","seq":5,"dialog_id":"stu_a","full_content":"哦！我懂了。","self_resolved":true}
// ↑ self_resolved=true 触发确定性队列弹出下一题 Q2
Server → Client: {"type":"student_new_question","seq":6,"dialog_id":"stu_a","question":Q2}
Client → Server: {"type":"teacher_message","dialog_id":"stu_a","text":"好，我们来看新问题。"}
Server → Client: {"type":"reply_chunk","seq":7,...}                             // 针对 Q2 的回复
Server → Client: {"type":"reply_end","seq":8,"dialog_id":"stu_a","full_content":"...","self_resolved":false}
... 多轮互动（若达 8 轮则 turn_limit 自动推进到 Q3）...
// 所有预生成题结束后，dialog 整体 resolved
Server → Client: {"type":"dialog_resolved","seq":N,"dialog_id":"stu_a","source":"self_resolve"}
```

**差异要点**：

- ``session_init.questions`` 的语义从"所有题"变为"每学生首问"（同原型，数量变少）
- ``student_new_question`` 帧：由确定性队列弹出（非 LLM 决策），出现在 ``reply_end(self_resolved=true)`` 之后，或当前题 turn 数达上限时
- **推进规则**：``self_resolved`` → 单题 ``resolved``；turn 数达上限 M=8 → 单题 ``abandoned(turn_limit)``；队列空 → 整个 dialog ``resolved``
- ``resolve``/``dialog_resolved`` 仍可使用——``teacher_marked`` 语义从"该题已解"升级为"结束整段辅导"（字段不变）
- 老前端运行 v2 服务端：遇到 ``student_new_question`` 未知类型静默丢弃，reply / resolve 流程仍可运行

### 3.6 关键不变式

- **流式 chunk 顺序**：同一 `dialog_id` 的 `reply_chunk` 序列保证按 `chunk_seq` 升序到达；后端不会把不同 dialog 的 chunk 交错（单 session 串行处理 `teacher_message`）
- **Hold-back 缓冲**：`reply_chunk.delta` **绝不会**包含末尾 `[懂了]` 标记字符（agent 侧已过滤）。前端可无脑拼接 delta；`reply_end` 到达时再用 `full_content` 校正一次显示文本
- **每个 reply 必有 end**：每个 `reply_chunk` 序列末尾一定跟一个 `reply_end`；连接断开视为流中断，前端显示"对话中断"标志
- **seq 单调递增**：服务端任意类型帧都共享同一 `seq` 计数器，从 0 起，每发一帧 +1
- **客户端→服务端 不带 seq**：对称性上略不一致，但客户端发送的帧少且无序约束，省下复杂度

### 3.7 与 Pydantic 模型对照

后端实现以 `backend/schemas/ws_events.py` 为权威来源；本节文档与该模块保持一致。
模型导出名速查：

| TS interface | Pydantic class |
|---|---|
| `SelectDialog` | `WsSelectDialog` |
| `TeacherMessage` | `WsTeacherMessage` |
| `Resolve` | `WsResolve` |
| `Abandon` | `WsAbandon` |
| `SessionInit` | `WsSessionInit` |
| `DialogActive` | `WsDialogActive` |
| `ReplyChunk` | `WsReplyChunk` |
| `ReplyEnd` | `WsReplyEnd` |
| `StudentNewQuestion` | `WsStudentNewQuestion` |
| `DialogResolved` | `WsDialogResolved` |
| `DialogAbandoned` | `WsDialogAbandoned` |
| `Summary` | `WsSummary` |
| `ErrorMessage` | `WsError` |
| `WsStudentInfo` | `WsStudentInfo` |
| `WsErrorCode` | `WsErrorCode` (Literal) |

前端如需自动同步类型，可后续补一个 `pydantic-to-typescript` 生成步骤；M2 阶段先手抄。

---

## 4. 人设 Personas

### 4.1 列出可用人设

**`GET /api/personas?stage_id=<stage_id>&subject_level=<subject_level>`**

- 支持过滤：`stage_id`、`subject_level`

**响应** `data`：

```ts
interface PersonaListItem {
  id: UUID;
  name: string;
  gender: string;
  grade: Grade;
  age: number;
  stage_id: string;
  subject_level: string;
  summary: string;                  // 一句话描述
}
```

### 4.2 获取人设详情

**`GET /api/personas/{name_or_id}`**

**响应**：返回单个人设详情（schema 见 `data/personas/_schema.json`；以当前实现为准）。

## 5. 阶段 Stages

### 5.1 列出阶段

**`GET /api/stages`**

**响应** `data`：

```ts
interface StageListItem {
  id: string;
  name: string;
  grade_range: string;
  age_range: string;
}
```

### 5.2 获取阶段详情

**`GET /api/stages/{stage_id}`**

**响应**：返回阶段详情；当前已实现的稳定概要字段同上.

---

## 6. 健康检查

**`GET /health`**

```ts
{ status: "ok", version: "0.1.0", uptime_seconds: 1234 }
```

---

## 7. 版本管理

- **当前版本**：`v0` — M1 到 M3 开发期间
- **语义变更规则**：
  - 新增字段 / 接口 = minor（不破坏）
  - 删除字段 / 改字段名 / 改语义 = major（须在 README Changelog 列出并通知全组）

---

## 8. Open Questions（待团队决定）

- [ ] 是否引入用户登录 / 鉴权？v0 假设**单用户本地**无鉴权
- [ ] 多个 session 并发上限？目前假设 1
- [ ] 语音输入（ASR）接入方式：直接在 WS 发 PCM 还是先 HTTP 上传再走 WS？
- [ ] 报告是否支持异步生成？若 > 5s 应改为轮询而非同步返回

---

## Changelog

| 版本 | 日期 | 变更 | 作者 |
|---|---|---|---|
| v0-draft | 2026-04-22 | 初稿 | Cascade |
| v1 (#71) | 2026-04-25 | §3 替换为 1v1 答疑陪练 WebSocket 协议（`/ws/qa-sessions/{session_id}`），废弃多学生课堂模型；新增 `backend/schemas/ws_events.py` Pydantic 模型作为权威 schema | A-Agent |
| v1 (#72) | 2026-04-28 | 新增 §2.5 — `/api/qa-sessions` 创建/查询/结束 REST 接口，对应 `backend/api/qa_sessions.py` 实现 | B-Full |
| v2-schema (#111) | 2026-04-28 | M3 连续答疑模式 schema 演进：`DialogMessage` 新增 `is_new_question` / `question_id`；WS 新增 `student_new_question` 帧；`DialogStateSummary.id` 语义扩展为 `student_id`。严格向后兼容，M2 行为不变。编排实现在后续 PR 切换 | A-Agent |
| v2-freeze (#121) | 2026-05-05 | **M3 协议冻结**：新增 §0.5 鉴权（Bearer JWT + WS `?token=` + close 4401 + 错误码 40101/40301）；新增 §2.6 评估报告（`GET /api/qa-sessions/{id}/evaluation` 三态机、`EvaluationReport`、`TeacherFeedback`）。`owner_id` 不进 REST body，从 JWT claim 取。schema 占位文件 `backend/schemas/evaluation.py` / `feedback.py`，真实实现见 #M3-A1 ~ #M3-B3 | A+B+C |
| v2-queue | 2026-05-06 | **M3 确定性队列重构**：移除 LLM 追问决策（`decide_followup`），改为预生成 N=3 题、确定性推进（`self_resolved` / `turn_limit` M=8）。`ResolutionSource` 新增 `turn_limit`；`DialogResolved.source` 扩展为完整 `ResolutionSource` 联合类型；§3.5.2 典型序列更新。`DialogSession` 新增 `asked_questions` / `question_progress` / `current_question_idx` 字段 | A-Agent |
