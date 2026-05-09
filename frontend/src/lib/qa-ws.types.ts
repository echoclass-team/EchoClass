/**
 * QA 答疑陪练 WebSocket 协议 TypeScript 类型。
 *
 * 与后端权威 schema `backend/schemas/ws_events.py` 一一对应。
 * 协议规范见 `docs/api_contract.md §3`。
 *
 * 维护约定：协议字段 / type 枚举 / 错误码任一变更须同步修改
 * 后端 schema + 本文件 + api_contract.md，并由 A+B 双 approve。
 */

// =============================================================== 嵌入业务对象

/** ISO-8601 时间戳字符串。 */
export type ISO8601 = string;

/** 教案元数据（与 REST 一致；前端按需取用）。 */
export interface LessonMeta {
  subject: string;
  grade: string;
  topic: string;
  objectives: string[];
  key_points: string[];
  difficult_points: string[];
}

/** 学生主动提出的问题。 */
export interface StudentQuestion {
  id: string;
  speaker_id: string;
  speaker_name: string;
  content: string;
  category:
    | "clarify_concept"
    | "challenge_example"
    | "extend_topic"
    | "off_topic"
    | "stuck_misconception";
  difficulty: "easy" | "medium" | "hard";
  linked_key_point?: string | null;
  linked_misconception_id?: string | null;
  rationale?: string;
  self_score?: number | null;
}

/** session_init 中传给前端的学生概要（轻量版 Persona，只 6 个字段）。 */
export interface WsStudentInfo {
  id: string;
  name: string;
  stage_id: string;
  /** "优秀" | "中等" | "薄弱" */
  subject_level: string;
  avatar_seed: string;
  /** 一句话概括人设。 */
  summary: string;
}

/** 解决方式来源。 */
export type ResolutionSource =
  | "self_resolve"
  | "teacher_marked"
  | "auto_evaluator"
  | "abandoned"
  | "turn_limit";

/** WS 错误码受控枚举。 */
export type WsErrorCode =
  | "dialog_not_found"
  | "dialog_already_ended"
  | "session_not_found"
  | "invalid_message"
  | "replaced"
  | "llm_failed"
  | "internal_error";

// ============================================================ 客户端 → 服务端

interface _ClientBase {
  /** 客户端发送时间，可选；服务端不做强校验。 */
  timestamp?: ISO8601;
}

export interface WsSelectDialog extends _ClientBase {
  type: "select_dialog";
  /** 目标对话 id（== StudentQuestion.id）。 */
  dialog_id: string;
}

export interface WsTeacherMessage extends _ClientBase {
  type: "teacher_message";
  dialog_id: string;
  /** 师范生本轮发言；非空。 */
  text: string;
}

export interface WsResolve extends _ClientBase {
  type: "resolve";
  dialog_id: string;
  /** 默认 "teacher_marked"。 */
  source?: "teacher_marked" | "self_resolve";
}

export interface WsAbandon extends _ClientBase {
  type: "abandon";
  dialog_id: string;
}

export type ClientMessage =
  | WsSelectDialog
  | WsTeacherMessage
  | WsResolve
  | WsAbandon;

export type ClientMessageType = ClientMessage["type"];

// ============================================================ 服务端 → 客户端

interface _ServerBase {
  /** 服务端单调递增帧序号（连接内唯一，从 0 起）。 */
  seq: number;
  timestamp: ISO8601;
}

export interface WsSessionInit extends _ServerBase {
  type: "session_init";
  session_id: string;
  lesson: LessonMeta;
  students: WsStudentInfo[];
  /** 学生主动构思好的问题队列，与 next_pending 顺序一致。 */
  questions: StudentQuestion[];
}

export interface WsDialogActive extends _ServerBase {
  type: "dialog_active";
  dialog_id: string;
}

export interface WsReplyChunk extends _ServerBase {
  type: "reply_chunk";
  dialog_id: string;
  /** 增量文本（已剥离 `[懂了]` 标记）。 */
  delta: string;
  /** 同 dialog 内 chunk 序号，从 0 递增。 */
  chunk_seq: number;
}

export interface WsReplyEnd extends _ServerBase {
  type: "reply_end";
  dialog_id: string;
  /** 完整回复（权威文本，已剥离标记）。 */
  full_content: string;
  /** LLM 是否在末尾标记了 [懂了]。 */
  self_resolved: boolean;
}

/** M3 连续答疑：学生在同一 dialog 内主动抛出新问题（追问）。 */
export interface WsStudentNewQuestion extends _ServerBase {
  type: "student_new_question";
  dialog_id: string;
  /** 学生主动抛出的新问题，复用 StudentQuestion 结构。 */
  question: StudentQuestion;
  /** 推进原因：'turn_limit' / 'self_resolve' 等；首问为 null。 */
  source?: string | null;
  /** 可选：本新问题是在哪一轮回复之后产生的；前端可忽略。 */
  after_reply_chunk_seq?: number | null;
}

export interface WsDialogResolved extends _ServerBase {
  type: "dialog_resolved";
  dialog_id: string;
  source: ResolutionSource;
}

export interface WsDialogAbandoned extends _ServerBase {
  type: "dialog_abandoned";
  dialog_id: string;
}

export interface WsSummary extends _ServerBase {
  type: "summary";
  /** QASession.summary() 返回结构（结构见 services/qa_session.py）。 */
  data: Record<string, unknown>;
}

export interface WsError extends _ServerBase {
  type: "error";
  code: WsErrorCode;
  message: string;
  dialog_id?: string;
}

export type ServerMessage =
  | WsSessionInit
  | WsDialogActive
  | WsReplyChunk
  | WsReplyEnd
  | WsStudentNewQuestion
  | WsDialogResolved
  | WsDialogAbandoned
  | WsSummary
  | WsError;

export type ServerMessageType = ServerMessage["type"];

/** 帮助函数：按 type 取出 ServerMessage 中的对应分支。 */
export type ServerMessageOf<T extends ServerMessageType> = Extract<
  ServerMessage,
  { type: T }
>;

// ====================================================================== 客户端

/** WS 连接当前状态。 */
export type QAWsStatus =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed"
  | "replaced";
