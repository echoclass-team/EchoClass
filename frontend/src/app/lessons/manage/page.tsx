"use client";

import Link from "next/link";
import { useMemo, useRef, useState, type ChangeEvent } from "react";
import { uploadLesson } from "@/lib/api/setup";
import { useSetup } from "@/components/setup/setup-provider";
import type { LessonLibraryItem } from "@/types/setup";

function toLessonLibraryItem(payload: Awaited<ReturnType<typeof uploadLesson>>): LessonLibraryItem {
  const now = new Date().toISOString();
  return {
    lessonId: payload.lesson_id,
    title: payload.topic,
    subtitle: `${payload.subject} · ${payload.grade}`,
    source: "local",
    status: "ready",
    createdAt: now,
    updatedAt: now,
    subject: payload.subject,
    grade: payload.grade,
    topic: payload.topic,
    objectives: payload.objectives,
    key_points: payload.key_points,
    difficult_points: payload.difficult_points,
  };
}

function formatTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

export default function LessonManagePage() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const { draft, updateDraft, library, addLesson, selectLesson } = useSetup();
  const [uploadMessage, setUploadMessage] = useState("本地暂存优先：先从当前教案库里选，再可上传补充。");
  const [uploading, setUploading] = useState(false);

  const selectedLessonId = draft.selectedLessonId ?? library.selectedLessonId;
  const selectedLesson = useMemo(() => library.items.find((item) => item.lessonId === selectedLessonId) ?? null, [library.items, selectedLessonId]);

  const handleChooseLesson = (lesson: LessonLibraryItem) => {
    selectLesson(lesson.lessonId);
    updateDraft({ selectedLessonId: lesson.lessonId });
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    setUploadMessage(`正在上传 ${file.name} …`);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", file.name.replace(/\.[^.]+$/, ""));
      const payload = await uploadLesson(formData);
      const lessonItem = toLessonLibraryItem(payload);
      addLesson(lessonItem);
      selectLesson(lessonItem.lessonId);
      updateDraft({ selectedLessonId: lessonItem.lessonId });
      setUploadMessage(`已写入本地教案库：${lessonItem.title}`);
    } catch (error) {
      setUploadMessage(error instanceof Error ? error.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  return (
    <main className="px-4 py-10 sm:px-6 lg:px-8">
      <section className="mx-auto max-w-5xl rounded-3xl border border-slate-200 bg-white/80 p-6 shadow-sm backdrop-blur-sm sm:p-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold tracking-[0.3em] text-sky-700 uppercase">本地教案库</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">教案管理页</h1>
            <p className="mt-3 text-sm leading-6 text-slate-600">这里优先展示本地暂存和已上传的教案，可直接选择当前使用的 lesson，也可以继续上传新教案。</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <button type="button" onClick={() => fileInputRef.current?.click()} className="rounded-full bg-slate-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800">上传教案</button>
            <p className="text-xs text-slate-500">上传后会立即写入本地教案库</p>
            <input ref={fileInputRef} type="file" className="hidden" accept=".pdf,.md,.txt,.doc,.docx" onChange={handleUpload} />
          </div>
        </div>
        <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">{uploading ? "上传中…" : uploadMessage}</div>
        <div className="mt-8">
          {library.items.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-sm leading-6 text-slate-600">
              <p className="font-medium text-slate-950">当前本地教案库为空</p>
              <p className="mt-2">这里会先显示本地暂存和已上传教案；你可以先点击“上传教案”添加第一份。</p>
            </div>
          ) : (
            <div className="grid gap-4">
              {library.items.map((item) => {
                const active = item.lessonId === selectedLessonId;
                return (
                  <button key={item.lessonId} type="button" onClick={() => handleChooseLesson(item)} className={`rounded-3xl border p-5 text-left transition ${active ? "border-sky-500 bg-sky-50" : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"}`}>
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h2 className="text-base font-semibold text-slate-950">{item.title ?? item.topic ?? item.lessonId}</h2>
                        <p className="mt-1 text-sm text-slate-600">{item.subject ?? "—"} · {item.grade ?? "—"}</p>
                      </div>
                      <span className={`rounded-full px-3 py-1 text-xs font-medium ${active ? "bg-sky-600 text-white" : "bg-slate-200 text-slate-700"}`}>{active ? "当前选中" : item.status}</span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
                      <span>状态：{item.status}</span>
                      <span>更新时间：{formatTime(item.updatedAt ?? item.createdAt)}</span>
                      <span>来源：{item.source}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <div className="mt-8 flex items-center justify-between gap-4 rounded-2xl bg-slate-950 px-4 py-3 text-sm text-white">
          <p>当前选中：{selectedLesson?.title ?? selectedLesson?.topic ?? selectedLesson?.lessonId ?? "未选择"}</p>
          <Link href={selectedLessonId ? `/setup/personas?lesson_id=${encodeURIComponent(selectedLessonId)}` : "/setup/personas"} className="text-sky-300 transition hover:text-sky-200">去模拟课堂</Link>
        </div>
      </section>
    </main>
  );
}
