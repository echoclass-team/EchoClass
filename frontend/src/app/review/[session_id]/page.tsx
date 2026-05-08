"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchQASessionState } from "@/lib/api/qa";
import { pollEvaluation } from "@/lib/evaluation";
import { DialogReplay } from "@/components/review/dialog-replay";
import { EvaluationPanel } from "@/components/review/evaluation-panel";
import { FeedbackPanel } from "@/components/review/feedback-panel";
import type { QASessionStateData, QASessionEvaluationData } from "@/types/qa";

export default function ReviewPage() {
  const params = useParams<{ session_id: string }>();
  const sessionId = params.session_id;

  const [session, setSession] = useState<QASessionStateData | null>(null);
  const [evalData, setEvalData] = useState<QASessionEvaluationData | null>(null);
  const [activeDialogId, setActiveDialogId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [evalPolling, setEvalPolling] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  // Load session detail
  const loadSession = useCallback(async () => {
    try {
      const data = await fetchQASessionState(sessionId);
      setSession(data);
      if (data.dialogs.length > 0 && !activeDialogId) {
        setActiveDialogId(data.dialogs[0].id);
      }
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "加载会话失败");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Load / poll evaluation
  const loadEvaluation = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setEvalPolling(true);
    const result = await pollEvaluation(sessionId, { signal: ac.signal });
    setEvalData(result);
    setEvalPolling(false);
  }, [sessionId]);

  const retryEvaluation = useCallback(() => {
    setEvalData(null);
    loadEvaluation();
  }, [loadEvaluation]);

  useEffect(() => {
    loadSession();
    loadEvaluation();
    return () => {
      abortRef.current?.abort();
    };
  }, [loadSession, loadEvaluation]);

  if (loadError) {
    return (
      <main className="px-4 py-10 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl">
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-center">
            <p className="text-sm text-rose-700">{loadError}</p>
            <Link
              href="/sessions"
              className="mt-4 inline-block rounded-full bg-slate-950 px-5 py-2 text-sm font-medium text-white"
            >
              返回列表
            </Link>
          </div>
        </div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="px-4 py-10 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-6xl">
          <div className="h-96 animate-pulse rounded-2xl border border-slate-200 bg-slate-100" />
        </div>
      </main>
    );
  }

  return (
    <main className="px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <Link
              href="/sessions"
              className="text-xs text-slate-400 transition hover:text-slate-600"
            >
              ← 返回列表
            </Link>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950">
              复盘：{session.lesson.topic || session.session_id}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {session.lesson.subject} · {session.lesson.grade} ·{" "}
              {session.dialogs.length} 个对话 ·{" "}
              已解答 {session.resolved} / 放弃 {session.abandoned}
            </p>
          </div>
        </div>

        {/* Main grid: left = dialog replay, right = eval + feedback */}
        <div className="grid gap-6 lg:grid-cols-5">
          {/* Dialog replay — takes 3 cols */}
          <div className="lg:col-span-3" style={{ minHeight: "28rem" }}>
            <DialogReplay
              dialogs={session.dialogs}
              activeId={activeDialogId}
              onSelect={setActiveDialogId}
            />
          </div>

          {/* Right column: evaluation + feedback — takes 2 cols */}
          <div className="space-y-6 lg:col-span-2">
            {/* Evaluation */}
            {evalPolling && !evalData && (
              <div className="rounded-2xl border border-slate-200 bg-white p-5">
                <h3 className="text-sm font-semibold tracking-wide text-slate-500 uppercase">
                  评估报告
                </h3>
                <div className="mt-4 flex items-center gap-3">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-sky-600" />
                  <span className="text-sm text-slate-500">
                    正在生成评估报告…
                  </span>
                </div>
              </div>
            )}

            {evalData?.status === "pending" && !evalPolling && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
                <h3 className="text-sm font-semibold tracking-wide text-amber-600 uppercase">
                  评估报告
                </h3>
                <p className="mt-2 text-sm text-amber-700">
                  评估超时未完成，可能仍在生成中。
                </p>
                <button
                  type="button"
                  onClick={retryEvaluation}
                  className="mt-3 rounded-full bg-amber-600 px-4 py-1.5 text-xs font-medium text-white transition hover:bg-amber-700"
                >
                  重试
                </button>
              </div>
            )}

            {evalData?.status === "failed" && (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5">
                <h3 className="text-sm font-semibold tracking-wide text-rose-600 uppercase">
                  评估报告
                </h3>
                <p className="mt-2 text-sm text-rose-700">
                  评估生成失败：{evalData.error ?? "未知错误"}
                </p>
                <button
                  type="button"
                  onClick={retryEvaluation}
                  className="mt-3 rounded-full bg-rose-600 px-4 py-1.5 text-xs font-medium text-white transition hover:bg-rose-700"
                >
                  重试
                </button>
              </div>
            )}

            {evalData?.status === "done" && evalData.evaluation && (
              <EvaluationPanel evaluation={evalData.evaluation} />
            )}

            {/* Feedback */}
            {evalData?.status === "done" && evalData.feedback && (
              <FeedbackPanel feedback={evalData.feedback} />
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
