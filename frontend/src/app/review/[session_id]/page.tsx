"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchQASessionState } from "@/lib/api/qa";
import { pollEvaluation } from "@/lib/evaluation";
import { DialogReplay } from "@/components/review/dialog-replay";
import { EvaluationPanel } from "@/components/review/evaluation-panel";
import { FeedbackPanel } from "@/components/review/feedback-panel";
import { buildReviewMarkdown, downloadMarkdown } from "@/lib/export-review-md";
import type { QASessionStateData, QASessionEvaluationData, DialogStateSummary } from "@/types/qa";

// --- helpers

const SOURCE_LABEL: Record<string, string> = {
  teacher_marked: "教师标记",
  self_resolve: "学生自悟",
  auto_evaluator: "自动评估",
  abandoned: "放弃",
  turn_limit: "轮次上限",
};

function deriveStudentsBreakdown(dialogs: DialogStateSummary[]) {
  const map = new Map<string, { name: string; resolved: number; abandoned: number; other: number }>();
  for (const d of dialogs) {
    const key = d.student_id;
    const entry = map.get(key) ?? { name: d.student_name, resolved: 0, abandoned: 0, other: 0 };
    if (d.status === "resolved") entry.resolved++;
    else if (d.status === "abandoned") entry.abandoned++;
    else entry.other++;
    map.set(key, entry);
  }
  return Array.from(map.entries()).map(([id, v]) => ({ id, ...v }));
}

function deriveResolutionSources(dialogs: DialogStateSummary[]) {
  const counts: Record<string, number> = {};
  for (const d of dialogs) {
    if (d.resolution_source) {
      counts[d.resolution_source] = (counts[d.resolution_source] ?? 0) + 1;
    }
  }
  return counts;
}

// --- page

export default function ReviewPage() {
  const params = useParams<{ session_id: string }>();
  const sessionId = params.session_id;

  const [session, setSession] = useState<QASessionStateData | null>(null);
  const [evalData, setEvalData] = useState<QASessionEvaluationData | null>(null);
  const [activeDialogId, setActiveDialogId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [evalPolling, setEvalPolling] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

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

  const loadEvaluation = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setEvalPolling(true);
    const result = await pollEvaluation(sessionId, { signal: ac.signal });
    if (abortRef.current !== ac) return;
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

  const total = session.resolved + session.abandoned + session.pending + session.active;
  const resolvedPct = total > 0 ? Math.round((session.resolved / total) * 100) : 0;
  const pending = session.pending + session.active;
  const students = deriveStudentsBreakdown(session.dialogs);
  const resSources = deriveResolutionSources(session.dialogs);

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
              {session.lesson.topic
                ? `《${session.lesson.topic}》答疑回顾`
                : "本次答疑回顾"}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {session.lesson.subject} · {session.lesson.grade} ·{" "}
              {session.dialogs.length} 个对话
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                const md = buildReviewMarkdown(
                  session,
                  evalData?.evaluation,
                  evalData?.feedback,
                );
                const name = session.lesson.topic || session.session_id;
                downloadMarkdown(md, `${name}-复盘.md`);
              }}
              className="rounded-full border border-slate-300 bg-white px-5 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
            >
              导出 MD
            </button>
            <Link
              href="/setup"
              className="rounded-full bg-slate-950 px-5 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
            >
              再来一次
            </Link>
            <Link
              href="/"
              className="text-sm text-slate-500 hover:text-slate-900"
            >
              回首页 →
            </Link>
          </div>
        </div>

        {/* Summary stats */}
        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <BigStat label="已解答" value={session.resolved} accent="emerald" sub={`${resolvedPct}% 完成`} />
          <BigStat
            label="已放弃"
            value={session.abandoned}
            accent="slate"
            sub={total > 0 ? `占 ${Math.round((session.abandoned / total) * 100)}%` : "—"}
          />
          <BigStat
            label="未完成"
            value={pending}
            accent={pending > 0 ? "amber" : "emerald"}
            sub={pending > 0 ? "提前结束遗留" : "全部处理完毕"}
          />
        </div>

        {/* Main grid: left = dialog replay, right = eval + feedback */}
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="lg:col-span-3" style={{ minHeight: "28rem" }}>
            <DialogReplay
              dialogs={session.dialogs}
              activeId={activeDialogId}
              onSelect={setActiveDialogId}
            />
          </div>

          <div className="space-y-6 lg:col-span-2">
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

            {evalData?.status === "done" && evalData.feedback && (
              <FeedbackPanel feedback={evalData.feedback} />
            )}
          </div>
        </div>

        {/* Bottom section: students breakdown + resolution sources */}
        {(students.length > 0 || Object.keys(resSources).length > 0) && (
          <div className="mt-8 grid gap-6 lg:grid-cols-2">
            {students.length > 0 && (
              <Card title="按学生维度">
                <ul className="space-y-3">
                  {students.map((s) => {
                    const sTotal = s.resolved + s.abandoned + s.other;
                    const rPct = sTotal > 0 ? (s.resolved / sTotal) * 100 : 0;
                    const aPct = sTotal > 0 ? (s.abandoned / sTotal) * 100 : 0;
                    return (
                      <li key={s.id}>
                        <div className="flex items-baseline justify-between gap-3 text-sm">
                          <span className="font-semibold text-slate-900">{s.name}</span>
                          <span className="text-xs text-slate-500">
                            {s.resolved} 解答 · {s.abandoned} 放弃 · {s.other} 其他
                          </span>
                        </div>
                        <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
                          <div className="h-full bg-emerald-500" style={{ width: `${rPct}%` }} />
                          <div
                            className="-mt-2 h-full bg-slate-300"
                            style={{ width: `${aPct}%`, marginLeft: `${rPct}%` }}
                          />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </Card>
            )}

            {Object.keys(resSources).length > 0 && (
              <Card title="解决方式分布">
                <ul className="grid gap-2 sm:grid-cols-2">
                  {Object.entries(resSources).map(([source, count]) => (
                    <li
                      key={source}
                      className="flex items-baseline justify-between rounded-xl bg-slate-50 px-4 py-2.5"
                    >
                      <span className="text-sm text-slate-700">
                        {SOURCE_LABEL[source] ?? source}
                      </span>
                      <span className="text-base font-semibold text-slate-950">{count}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

// --- blocks

function BigStat({
  label,
  value,
  accent,
  sub,
}: {
  label: string;
  value: number;
  accent: "emerald" | "slate" | "amber";
  sub?: string;
}) {
  const accentClass = {
    emerald: "from-emerald-500 to-emerald-600 text-white",
    slate: "from-slate-700 to-slate-900 text-white",
    amber: "from-amber-500 to-amber-600 text-white",
  }[accent];
  return (
    <div className={`rounded-3xl bg-gradient-to-br p-5 shadow-md ${accentClass}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/80">{label}</p>
      <p className="mt-2 text-4xl font-semibold leading-none">{value}</p>
      {sub && <p className="mt-2 text-sm text-white/85">{sub}</p>}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="text-sm font-semibold tracking-[0.2em] text-slate-700 uppercase">
        {title}
      </h2>
      <div className="mt-4">{children}</div>
    </div>
  );
}
