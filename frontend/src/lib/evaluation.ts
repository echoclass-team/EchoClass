/**
 * Evaluation polling utility for the review page.
 *
 * Polls GET /api/qa-sessions/{id}/evaluation every `intervalMs` until
 * status !== "pending" or `timeoutMs` elapsed.
 */

import { fetchEvaluation } from "@/lib/api/qa";
import type { QASessionEvaluationData } from "@/types/qa";

export interface PollOptions {
  intervalMs?: number;
  timeoutMs?: number;
  signal?: AbortSignal;
}

const DEFAULT_INTERVAL = 2_000;
const DEFAULT_TIMEOUT = 60_000;

/**
 * Poll evaluation endpoint until done/failed or timeout.
 *
 * Returns the final evaluation data. If timeout is reached while still
 * pending, returns `{ status: "pending" }` so the caller can show a retry.
 */
export async function pollEvaluation(
  sessionId: string,
  opts: PollOptions = {},
): Promise<QASessionEvaluationData> {
  const interval = opts.intervalMs ?? DEFAULT_INTERVAL;
  const timeout = opts.timeoutMs ?? DEFAULT_TIMEOUT;
  const signal = opts.signal;

  const deadline = Date.now() + timeout;

  while (Date.now() < deadline) {
    if (signal?.aborted) {
      return { status: "pending" };
    }

    try {
      const data = await fetchEvaluation(sessionId);
      if (data.status !== "pending") {
        return data;
      }
    } catch {
      // Network error or 4xx/5xx — stop polling, let caller handle
      return { status: "failed", error: "network_error" };
    }

    // Wait before next poll
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(resolve, interval);
      signal?.addEventListener(
        "abort",
        () => {
          clearTimeout(timer);
          reject(new DOMException("Aborted", "AbortError"));
        },
        { once: true },
      );
    }).catch(() => {
      // Aborted — return pending
    });
  }

  // Timeout reached
  return { status: "pending" };
}
