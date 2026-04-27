/**
 * 临时缓存 QA session 的 summary 数据，跨页面（陪练页 → summary 页）传递。
 *
 * 为什么用 sessionStorage：
 * - `POST /api/qa-sessions/{id}/end` 只能成功调用一次（pop registry 后 404），
 *   summary 必须在调用瞬间保存下来；不能让 summary 页自己再发请求
 * - Next 14 App Router 不便用 router state 做跨页面传值
 * - sessionStorage 比 localStorage 更合适：标签页关闭即清，不污染下次会话
 *
 * Key 设计：按 session_id 区分；防止多窗口陪练串味。
 */

import type { QASessionSummary } from "@/types/qa";

const PREFIX = "echoclass.qa.summary.";

export function saveQASummary(sessionId: string, summary: QASessionSummary): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(PREFIX + sessionId, JSON.stringify(summary));
  } catch {
    // sessionStorage 可能在隐私模式 / 配额满时抛错；忽略，summary 页会显示降级提示
  }
}

export function loadQASummary(sessionId: string): QASessionSummary | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(PREFIX + sessionId);
    return raw ? (JSON.parse(raw) as QASessionSummary) : null;
  } catch {
    return null;
  }
}

export function clearQASummary(sessionId: string): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(PREFIX + sessionId);
}
