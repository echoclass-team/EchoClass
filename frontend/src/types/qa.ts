/**
 * QA 答疑陪练 REST 接口的请求 / 响应类型。
 *
 * 与后端 `backend/schemas/qa_session_api.py` 一一对应，字段命名保持
 * snake_case（与 ApiResponse 包络解开后直接对齐）。
 *
 * 注意：WS 协议类型在 `@/lib/qa-ws.types`，与本文件不要互相 import；
 * 二者通过共享的 `WsStudentInfo` / `StudentQuestion` / `LessonMeta` 共形（重新声明）。
 */

import type { LessonMeta, StudentQuestion, WsStudentInfo, ResolutionSource } from "@/lib/qa-ws.types";

/** GET /api/lessons/{id}/recommended-personas data */
export interface RecommendedPersonasData {
  lesson_id: string;
  subject: string;
  grade: string;
  topic: string;
  stage_id: string;
  stage_name: string;
  recommended_count: number;
  persona_ids: string[];
  /** PersonaSummary[] —— 与 GET /api/personas 同形 */
  students: Array<{
    id: string;
    name: string;
    gender: string;
    grade: string;
    age: number;
    stage_id: string;
    subject_level: string;
    summary: string;
  }>;
}

/** POST /api/qa-sessions 请求体 */
export interface CreateQASessionReq {
  lesson_id: string;
  persona_ids: string[];
  count_per_student?: number;
}

/** POST /api/qa-sessions 响应 data */
export interface CreateQASessionData {
  session_id: string;
  ws_url: string;
  lesson: LessonMeta;
  students: WsStudentInfo[];
  questions: StudentQuestion[];
}

export type DialogStatus = "pending" | "active" | "resolved" | "abandoned";

/** GET /api/qa-sessions/{id} 中的 dialogs[i] 元素 */
export interface DialogStateSummary {
  id: string;
  student_id: string;
  student_name: string;
  status: DialogStatus;
  question_preview: string;
  turn_count: number;
  resolution_source?: ResolutionSource;
}

/** GET /api/qa-sessions/{id} 响应 data */
export interface QASessionStateData {
  session_id: string;
  lesson: LessonMeta;
  students: WsStudentInfo[];
  dialogs: DialogStateSummary[];
  pending: number;
  active: number;
  resolved: number;
  abandoned: number;
}

/**
 * POST /api/qa-sessions/{id}/end 响应 data 中 summary 子字段。
 *
 * 字段宽松：后端 `QASession.summary()` 返回 `dict[str, Any]`，UI 安全访问。
 * 当前已知字段如下，未来扩展无需改前端类型。
 */
export interface QASessionSummary {
  session_id: string;
  lesson_topic?: string;
  total_questions?: number;
  resolved?: number;
  abandoned?: number;
  pending?: number;
  active?: number;
  covered_key_points?: string[];
  broken_misconception_ids?: string[];
  resolution_sources?: Record<string, number>;
  students_breakdown?: Array<{
    id: string;
    name: string;
    resolved?: number;
    abandoned?: number;
    pending?: number;
  }>;
  [key: string]: unknown;
}

/** POST /api/qa-sessions/{id}/end 响应 data */
export interface QASessionEndData {
  session_id: string;
  summary: QASessionSummary;
}
