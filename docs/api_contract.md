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

---

## 3. WebSocket `/ws/sessions/{session_id}`

### 3.1 连接

- **URL**：`ws://localhost:8000/ws/sessions/{session_id}?token=<opaque>`
- **协议**：文本帧，**每帧一条 JSON**（JSON Lines）
- **心跳**：客户端每 30s 发 `{"type":"ping"}`，服务端回 `{"type":"pong"}`
- **关闭码**：
  - `1000` 正常关闭
  - `4001` 鉴权失败
  - `4004` 会话不存在
  - `4009` 会话已结束

### 3.2 客户端 → 服务端

```ts
type ClientMessage =
  | TeacherUtterance
  | TeacherAction
  | Ping;

interface TeacherUtterance {
  type: "teacher_utterance";
  utterance_id: UUID;               // 客户端生成
  content: string;
  sent_at: ISO8601;
}

interface TeacherAction {
  type: "teacher_action";
  action: "call_on_student" | "pause" | "resume" | "write_on_board";
  payload: {
    speaker_id?: string;            // call_on_student 用
    text?: string;                  // write_on_board 用
  };
}

interface Ping { type: "ping"; }
```

### 3.3 服务端 → 客户端

```ts
type ServerMessage =
  | StudentReplyStart
  | StudentReplyChunk
  | StudentReplyEnd
  | DirectorEvent
  | BoardUpdate
  | SessionEnd
  | ErrorMessage
  | Pong;

interface StudentReplyStart {
  type: "student_reply_start";
  reply_id: UUID;                   // 本条发言 ID
  speaker_id: string;
  intent: "answer_question" | "ask_question" | "off_topic" | "passive";
  emotion: "neutral" | "curious" | "confused" | "confident" | "distracted";
  trigger: "teacher_prompt" | "spontaneous" | "peer_reaction";
  started_at: ISO8601;
}

interface StudentReplyChunk {
  type: "student_reply_chunk";
  reply_id: UUID;
  delta: string;                    // 增量 token
  seq: number;                      // 从 0 递增
}

interface StudentReplyEnd {
  type: "student_reply_end";
  reply_id: UUID;
  full_content: string;             // 完整文本（用于客户端校验）
  ended_at: ISO8601;
}

interface DirectorEvent {
  type: "director_event";
  event: "hand_raise" | "whisper" | "distraction" | "group_noise";
  speaker_id?: string;              // 若事件针对特定学生
  description: string;
}

interface BoardUpdate {
  type: "board_update";
  taught_points: string[];          // 全量（不是 diff），方便前端直接渲染
}

interface SessionEnd {
  type: "session_end";
  reason: "teacher_ended" | "timeout" | "error";
  summary_url: string;              // 指向 /api/sessions/{id}/report
}

interface ErrorMessage {
  type: "error";
  code: number;
  message: string;
}

interface Pong { type: "pong"; }
```

### 3.4 典型消息序列

```
Client → Server: {"type":"teacher_utterance", "content":"什么是分数？", ...}
Server → Client: {"type":"director_event", "event":"hand_raise", "speaker_id":"stu_01", ...}
Server → Client: {"type":"student_reply_start", "reply_id":"r1", "speaker_id":"stu_01", ...}
Server → Client: {"type":"student_reply_chunk", "reply_id":"r1", "delta":"分数就是", "seq":0}
Server → Client: {"type":"student_reply_chunk", "reply_id":"r1", "delta":"…一个数字…", "seq":1}
Server → Client: {"type":"student_reply_end",   "reply_id":"r1", ...}
Server → Client: {"type":"student_reply_start", "reply_id":"r2", "speaker_id":"stu_03", ...}
...（多个学生可能并发，通过 reply_id 区分）
Server → Client: {"type":"board_update", "taught_points":["分数的定义","1/2 示例"]}
```

**关键不变式**：
- 任意时刻，一个 `reply_id` 的 chunk 必须按 `seq` 顺序；前端收到乱序需丢弃或 reorder。
- 多个学生并发发言时，多个 `reply_id` 的 chunk 可以交错。
- 每个 `start` 必有对应 `end`；没有 `end` 视为流中断，前端显示"对话中断"标志。

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
