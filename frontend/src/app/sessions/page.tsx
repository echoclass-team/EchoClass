"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { fetchSessionList, deleteSession } from "@/lib/api/qa";
import type { QASessionListItem } from "@/types/qa";

function formatTime(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("zh-CN", { hour12: false });
}

function statusBadge(status: string) {
  switch (status) {
    case "active":
      return (
        <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
          进行中
        </span>
      );
    case "closed":
      return (
        <span className="rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-600">
          已结束
        </span>
      );
    default:
      return (
        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700">
          {status}
        </span>
      );
  }
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<QASessionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchSessionList();
      list.sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
      setSessions(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleDelete = useCallback(
    async (sessionId: string, e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!window.confirm("确定删除该陪练记录？关联的对话和评估数据将一并删除，不可恢复。")) {
        return;
      }
      setDeleting(sessionId);
      try {
        await deleteSession(sessionId);
        setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      } catch (err) {
        alert(err instanceof Error ? err.message : "删除失败");
      } finally {
        setDeleting(null);
      }
    },
    [],
  );

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="px-4 py-10 sm:px-6 lg:px-8">
      <section className="mx-auto max-w-4xl">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold tracking-[0.3em] text-sky-700 uppercase">
              历史复盘
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
              陪练记录
            </h1>
            <p className="mt-2 text-sm text-slate-600">
              查看过往答疑陪练记录，点击进入复盘页查看评估报告和反馈建议。
            </p>
          </div>
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
          >
            {loading ? "加载中…" : "刷新"}
          </button>
        </div>

        <div className="mt-8">
          {loading && sessions.length === 0 && (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-24 animate-pulse rounded-2xl border border-slate-200 bg-slate-100"
                />
              ))}
            </div>
          )}

          {error && (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">
              {error}
            </div>
          )}

          {!loading && !error && sessions.length === 0 && (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
              <p className="font-medium text-slate-700">暂无陪练记录</p>
              <p className="mt-2 text-sm text-slate-500">
                完成一次陪练后，记录会出现在这里。
              </p>
              <Link
                href="/setup"
                className="mt-4 inline-block rounded-full bg-slate-950 px-5 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
              >
                开始陪练
              </Link>
            </div>
          )}

          {sessions.length > 0 && (
            <div className="grid gap-4">
              {sessions.map((s) => (
                <Link
                  key={s.session_id}
                  href={`/review/${encodeURIComponent(s.session_id)}`}
                  className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-slate-300 hover:shadow-sm"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h2 className="truncate text-base font-semibold text-slate-950">
                          {s.lesson_id}
                        </h2>
                        {statusBadge(s.status)}
                      </div>
                      <p className="mt-1.5 text-sm text-slate-500">
                        学生数 {s.persona_ids.length} · 创建于{" "}
                        {formatTime(s.created_at)}
                        {s.closed_at && ` · 结束于 ${formatTime(s.closed_at)}`}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={(e) => handleDelete(s.session_id, e)}
                        disabled={deleting === s.session_id}
                        className="rounded-full border border-rose-200 bg-white px-3 py-1 text-xs font-medium text-rose-600 transition hover:bg-rose-50 disabled:opacity-50"
                      >
                        {deleting === s.session_id ? "删除中…" : "删除"}
                      </button>
                      <span className="text-sm text-slate-400 transition group-hover:text-slate-600">
                        查看复盘 →
                      </span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
