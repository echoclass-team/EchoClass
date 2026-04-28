"use client";

/**
 * #B6: 陪练总结页。
 *
 * 数据来源：sessionStorage 中由 `QASessionView.handleEnd` 写入的 summary。
 * 因为 `POST /api/qa-sessions/{id}/end` 是一次性的（pop registry 后再调 404），
 * 不能在这里重新发请求；必须依赖前一页缓存。
 *
 * 失败兜底：
 * - URL 直达 / 刷新后 sessionStorage 丢失 → 显示降级提示，引导回 setup
 * - summary 字段不全 → 安全访问 + 占位
 *
 * UI 元素（对照 handoff §B6）：
 * - 顶部大数字：解答 / 放弃 / 总数
 * - 教学重点覆盖列表
 * - 破除迷思列表（仅展示 id；name 反查留给 M3 改进）
 * - 学生维度进度条
 * - 操作：再来一次（回 /setup）/ 导出报告（M3，先灰掉）
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { clearQASummary, loadQASummary } from "@/lib/qa-summary-storage";
import type { QASessionSummary } from "@/types/qa";

export default function QASummaryPage({
  params,
}: {
  params: { session_id: string };
}) {
  const router = useRouter();
  const sessionId = params.session_id;
  const [summary, setSummary] = useState<QASessionSummary | null | "missing">(
    null,
  );

  useEffect(() => {
    const stored = loadQASummary(sessionId);
    setSummary(stored ?? "missing");
  }, [sessionId]);

  if (summary === null) {
    // 还在加载（首挂载到读完 sessionStorage 的瞬间）
    return (
      <main className="px-6 py-12 text-center text-sm text-slate-500">
        正在加载总结…
      </main>
    );
  }

  if (summary === "missing") {
    return <SummaryMissing sessionId={sessionId} />;
  }

  const total = summary.total_questions ?? 0;
  const resolved = summary.resolved ?? 0;
  const abandoned = summary.abandoned ?? 0;
  const pending = (summary.pending ?? 0) + (summary.active ?? 0);
  const resolvedPct = total > 0 ? Math.round((resolved / total) * 100) : 0;

  const handleReset = () => {
    clearQASummary(sessionId);
    router.push("/setup");
  };

  return (
    <main className="relative overflow-hidden px-6 py-10 sm:px-10 lg:px-12">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_right,_rgba(16,185,129,0.16),_transparent_30%),linear-gradient(180deg,_rgba(248,250,252,1),_rgba(241,245,249,0.9))]" />

      <section className="mx-auto w-full max-w-5xl">
        <div>
          <p className="text-xs font-semibold tracking-[0.32em] text-emerald-700 uppercase">
            陪练总结
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
            {summary.lesson_topic
              ? `《${summary.lesson_topic}》答疑回顾`
              : "本次答疑回顾"}
          </h1>
          <p className="mt-3 font-mono text-xs text-slate-400">{sessionId}</p>
        </div>

        {/* 顶部大数字 */}
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          <BigStat label="已解答" value={resolved} accent="emerald" sub={`${resolvedPct}% 完成`} />
          <BigStat
            label="已放弃"
            value={abandoned}
            accent="slate"
            sub={total > 0 ? `占 ${Math.round((abandoned / total) * 100)}%` : "—"}
          />
          <BigStat
            label="未完成"
            value={pending}
            accent={pending > 0 ? "amber" : "emerald"}
            sub={pending > 0 ? "提前结束遗留" : "全部处理完毕"}
          />
        </div>

        {/* 教学重点 + 迷思 */}
        <div className="mt-10 grid gap-6 lg:grid-cols-2">
          <Card title="教学重点覆盖">
            <ListBlock
              items={summary.covered_key_points ?? []}
              empty="未匹配到具体重点。"
            />
          </Card>
          <Card title="破除迷思">
            <ListBlock
              items={summary.broken_misconception_ids ?? []}
              empty="本次没有触发迷思相关问题。"
              renderItem={(id) => (
                <span className="font-mono text-xs text-slate-700">{id}</span>
              )}
            />
          </Card>
        </div>

        {/* 学生维度 */}
        {summary.students_breakdown && summary.students_breakdown.length > 0 && (
          <div className="mt-10">
            <Card title="按学生维度">
              <ul className="space-y-3">
                {summary.students_breakdown.map((s) => (
                  <StudentRow key={s.id} student={s} />
                ))}
              </ul>
            </Card>
          </div>
        )}

        {/* 解决方式分布 */}
        {summary.resolution_sources && Object.keys(summary.resolution_sources).length > 0 && (
          <div className="mt-10">
            <Card title="解决方式分布">
              <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {Object.entries(summary.resolution_sources).map(([source, count]) => (
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
          </div>
        )}

        {/* 操作 */}
        <div className="mt-12 flex flex-wrap items-center gap-4">
          <button
            type="button"
            onClick={handleReset}
            className="inline-flex items-center justify-center rounded-full bg-slate-950 px-7 py-3 text-base font-semibold text-white shadow-md shadow-slate-950/20 transition hover:-translate-y-0.5 hover:bg-slate-800"
          >
            再来一次
          </button>
          <button
            type="button"
            disabled
            title="导出报告将于 M3 上线"
            className="inline-flex cursor-not-allowed items-center justify-center rounded-full border border-slate-200 bg-white px-6 py-3 text-base font-medium text-slate-400"
          >
            导出报告（M3）
          </button>
          <Link
            href="/"
            className="ml-auto text-sm text-slate-500 hover:text-slate-900"
          >
            回首页 →
          </Link>
        </div>
      </section>
    </main>
  );
}

const SOURCE_LABEL: Record<string, string> = {
  teacher_marked: "教师标记",
  self_resolve: "学生自悟",
  auto_evaluator: "自动评估",
  abandoned: "放弃",
};

// ============================================================ blocks

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
    <div className={`rounded-3xl bg-gradient-to-br p-6 shadow-md ${accentClass}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/80">{label}</p>
      <p className="mt-3 text-5xl font-semibold leading-none">{value}</p>
      {sub && <p className="mt-3 text-sm text-white/85">{sub}</p>}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-sm font-semibold tracking-[0.2em] text-slate-700 uppercase">
        {title}
      </h2>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function ListBlock({
  items,
  empty,
  renderItem,
}: {
  items: string[];
  empty: string;
  renderItem?: (item: string) => React.ReactNode;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-slate-400">{empty}</p>;
  }
  return (
    <ul className="space-y-2">
      {items.map((item, idx) => (
        <li key={idx} className="flex items-start gap-2 text-sm text-slate-800">
          <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-emerald-500" aria-hidden />
          <span className="leading-snug">{renderItem ? renderItem(item) : item}</span>
        </li>
      ))}
    </ul>
  );
}

function StudentRow({
  student,
}: {
  student: NonNullable<QASessionSummary["students_breakdown"]>[number];
}) {
  const r = student.resolved ?? 0;
  const a = student.abandoned ?? 0;
  const p = student.pending ?? 0;
  const total = r + a + p;
  const resolvedPct = total > 0 ? (r / total) * 100 : 0;
  const abandonedPct = total > 0 ? (a / total) * 100 : 0;
  return (
    <li>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-semibold text-slate-900">{student.name}</span>
        <span className="text-xs text-slate-500">
          {r} 解答 · {a} 放弃 · {p} 未完成
        </span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full bg-emerald-500"
          style={{ width: `${resolvedPct}%` }}
        />
        <div
          className="-mt-2 h-full bg-slate-300"
          style={{ width: `${abandonedPct}%`, marginLeft: `${resolvedPct}%` }}
        />
      </div>
    </li>
  );
}

function SummaryMissing({ sessionId }: { sessionId: string }) {
  return (
    <main className="px-6 py-16 sm:px-10">
      <section className="mx-auto max-w-2xl rounded-3xl border border-amber-200 bg-amber-50 p-8 text-center">
        <p className="text-xs font-semibold tracking-[0.32em] text-amber-700 uppercase">
          总结数据已不可用
        </p>
        <h1 className="mt-3 text-2xl font-semibold text-slate-950">
          没找到这次陪练的总结。
        </h1>
        <p className="mt-3 text-sm text-slate-600">
          可能原因：直接打开了本链接、刷新了页面、或浏览器清理了 sessionStorage。
          后端的 session 数据在结束时会清空，无法重建总结。
        </p>
        <p className="mt-3 font-mono text-xs text-slate-500">{sessionId}</p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/setup"
            className="inline-flex items-center justify-center rounded-full bg-slate-950 px-6 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800"
          >
            再开一次陪练
          </Link>
          <Link
            href="/"
            className="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white px-6 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            回首页
          </Link>
        </div>
      </section>
    </main>
  );
}
