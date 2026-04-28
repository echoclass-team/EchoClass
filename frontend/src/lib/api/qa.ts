/**
 * QA 答疑陪练 REST 客户端封装。对应后端 `backend/api/qa_sessions.py` 三个端点
 * + `GET /api/lessons/{id}/recommended-personas`。
 *
 * 设计：和 `lib/api/setup.ts` 对称 —— 使用 `apiFetch` + 解包 envelope，
 * 失败抛 `ApiError`（已带 status / code / message）。
 */

import { apiFetch } from "./client";
import type {
  CreateQASessionData,
  CreateQASessionReq,
  QASessionEndData,
  QASessionStateData,
  RecommendedPersonasData,
} from "@/types/qa";

function unwrap<T>(data: T | null, fallbackMessage: string): T {
  if (data === null) throw new Error(fallbackMessage);
  return data;
}

/** GET /api/lessons/{lesson_id}/recommended-personas */
export async function fetchRecommendedPersonas(lessonId: string, count?: number) {
  const search = new URLSearchParams();
  if (typeof count === "number") search.set("count", String(count));
  const qs = search.toString();
  const path = `/api/lessons/${encodeURIComponent(lessonId)}/recommended-personas${qs ? `?${qs}` : ""}`;
  return unwrap(
    (await apiFetch<RecommendedPersonasData>(path)).data,
    "Failed to load recommended personas",
  );
}

/** POST /api/qa-sessions —— 创建一次答疑陪练 session。 */
export async function createQASession(req: CreateQASessionReq) {
  return unwrap(
    (
      await apiFetch<CreateQASessionData>("/api/qa-sessions", {
        method: "POST",
        body: JSON.stringify(req),
      })
    ).data,
    "Failed to create qa session",
  );
}

/** GET /api/qa-sessions/{session_id} —— 查询当前状态（页面刷新 / 兜底）。 */
export async function fetchQASessionState(sessionId: string) {
  return unwrap(
    (
      await apiFetch<QASessionStateData>(
        `/api/qa-sessions/${encodeURIComponent(sessionId)}`,
      )
    ).data,
    "Failed to load qa session state",
  );
}

/** POST /api/qa-sessions/{session_id}/end —— 显式结束 session 并取 summary。 */
export async function endQASession(sessionId: string) {
  return unwrap(
    (
      await apiFetch<QASessionEndData>(
        `/api/qa-sessions/${encodeURIComponent(sessionId)}/end`,
        { method: "POST" },
      )
    ).data,
    "Failed to end qa session",
  );
}
