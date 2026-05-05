"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getLessonLibrary, getSetupDraft } from "@/lib/setup-storage";
import type { LessonLibraryState, SetupDraft } from "@/types/setup";

export default function ClassroomDemoPage() {
  const [draft, setDraft] = useState<SetupDraft>(getSetupDraft());
  const [library, setLibrary] = useState<LessonLibraryState>(getLessonLibrary());

  useEffect(() => {
    setDraft(getSetupDraft());
    setLibrary(getLessonLibrary());
  }, []);

  const selectedLessonId = draft.selectedLessonId ?? library.selectedLessonId;
  const selectedLesson = useMemo(
    () => library.items.find((item) => item.lessonId === selectedLessonId) ?? null,
    [library.items, selectedLessonId],
  );

  return (
    <main className="relative overflow-hidden px-6 py-10 sm:px-10 lg:px-12">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top,_rgba(15,23,42,0.12),_transparent_34%),linear-gradient(180deg,_rgba(248,250,252,1),_rgba(241,245,249,0.9))]" />

      <section className="mx-auto w-full max-w-6xl">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold tracking-[0.32em] text-sky-700 uppercase">课堂演示 / 本地摘要</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
            课堂演示已读取本地配置。
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
            当前页面只读取本地 draft 和教案库；实时互动、消息流和教师控制台尚未接后端。
          </p>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-3xl border border-slate-200 bg-slate-950 p-6 text-white shadow-lg shadow-slate-950/10 sm:p-8">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-slate-300">课堂舞台</p>
                <h2 className="mt-1 text-2xl font-semibold">实时互动未接后端</h2>
              </div>
              <span className="rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-medium text-slate-200">
                本地演示
              </span>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-3">
              <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs tracking-[0.2em] text-slate-400 uppercase">学段</p>
                <p className="mt-2 text-lg font-semibold">{draft.selectedStageId ?? "未选择"}</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">读取自 setup draft</p>
              </div>
              <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs tracking-[0.2em] text-slate-400 uppercase">教案</p>
                <p className="mt-2 text-lg font-semibold">{selectedLesson?.title ?? selectedLesson?.topic ?? "未选择"}</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">来自本地教案库</p>
              </div>
              <div className="rounded-3xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs tracking-[0.2em] text-slate-400 uppercase">学生</p>
                <p className="mt-2 text-lg font-semibold">{draft.selectedPersonaIds.length > 0 ? `${draft.selectedPersonaIds.length} 位` : "未选择"}</p>
                <p className="mt-2 text-sm leading-6 text-slate-300">仅回显本地草稿</p>
              </div>
            </div>

            <div className="mt-6 rounded-3xl border border-dashed border-white/15 bg-white/5 p-6">
              <p className="text-sm font-medium text-slate-300">互动区占位</p>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                这里后续会接入课堂消息、学生发言和教师控制台；当前只保留静态布局和本地配置回显。
              </p>
              <div className="mt-6 grid gap-3 md:grid-cols-2">
                <div className="rounded-2xl bg-black/20 p-4 text-sm text-slate-200">
                  课堂联机：开发中
                </div>
                <div className="rounded-2xl bg-black/20 p-4 text-sm text-slate-200">
                  本地暂存：已读取
                </div>
              </div>
            </div>
          </section>

          <aside className="space-y-6">
            <section className="rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-sm backdrop-blur-sm sm:p-8">
              <p className="text-sm font-medium text-slate-500">配置摘要</p>
              <h2 className="mt-1 text-2xl font-semibold text-slate-950">当前读到的状态</h2>
              <div className="mt-5 grid gap-3 text-sm leading-6 text-slate-600">
                <p><span className="text-slate-500">学段：</span>{draft.selectedStageId ?? "未选择"}</p>
                <p><span className="text-slate-500">教案：</span>{selectedLesson?.title ?? selectedLesson?.lessonId ?? "未选择"}</p>
                <p><span className="text-slate-500">学生：</span>{draft.selectedPersonaIds.length > 0 ? draft.selectedPersonaIds.join("、") : "未选择"}</p>
              </div>
              <p className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                课堂演示明确标记为本地摘要页，避免误认为实时互动已联机。
              </p>
            </section>

            <section className="rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-sm backdrop-blur-sm sm:p-8">
              <p className="text-sm font-medium text-slate-500">返回入口</p>
              <h2 className="mt-1 text-2xl font-semibold text-slate-950">继续修改配置</h2>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                可以回到配置页重新选教案与学生，或返回学段页从头演练。
              </p>
              <div className="mt-6 grid gap-3">
                <Link
                  href="/setup/personas"
                  className="inline-flex items-center justify-center rounded-2xl bg-slate-950 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800"
                >
                  返回选学生
                </Link>
                <Link
                  href="/setup/stage"
                  className="inline-flex items-center justify-center rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-medium text-slate-950 transition hover:border-slate-400 hover:bg-slate-50"
                >
                  重新选学段
                </Link>
              </div>
            </section>
          </aside>
        </div>
      </section>
    </main>
  );
}
