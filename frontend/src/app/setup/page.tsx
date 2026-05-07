"use client";

/**
 * #B4 Step 1: 上传教案 / 选已有教案。
 *
 * 流程：
 * - 拖拽 / 点选上传 PDF / MD / TXT → POST /api/lessons/upload（≈ 5-15s LLM 抽取）
 * - 成功后展示 LessonMeta 卡片 + 写入 localStorage lesson library
 * - "下一步：选学生" → 跳 /setup/personas?lesson_id=...
 * - 历史教案库点击即选（不重新上传）
 *
 * 状态：
 * - 上传过程用本地 useState，不依赖 SetupProvider（M2 1v1 流程独立）
 * - 选中 lesson 后 query 跳转，下一页通过 ?lesson_id 接管
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from "react";

import { fetchLessons, type LessonListItem, uploadLesson } from "@/lib/api/setup";
import type { LessonLibraryItem, LessonLibraryState } from "@/types/setup";

const ACCEPTED = ".pdf,.md,.markdown,.txt";

type UploadState =
  | { kind: "idle" }
  | { kind: "uploading"; filename: string }
  | { kind: "error"; message: string };

export default function SetupStep1Page() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [library, setLibrary] = useState<LessonLibraryState>({
    items: [],
    selectedLessonId: null,
  });
  const [uploadState, setUploadState] = useState<UploadState>({ kind: "idle" });
  const [dragOver, setDragOver] = useState(false);

  // 从数据库加载当前用户教案（取代 localStorage）
  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const rows = await fetchLessons();
        if (!active) return;
        const items: LessonLibraryItem[] = rows.map((r: LessonListItem) => ({
          lessonId: r.lesson_id,
          title: r.title || r.topic,
          subtitle: `${r.subject} · ${r.grade}`,
          subject: r.subject,
          grade: r.grade,
          topic: r.topic,
          source: "local" as const,
          status: "ready" as const,
          createdAt: r.created_at,
          objectives: r.objectives,
          key_points: r.key_points,
          difficult_points: r.difficult_points,
        }));
        setLibrary((prev) => ({ items, selectedLessonId: prev.selectedLessonId }));
      } catch {
        // 未登录 / 网络失败时静默
      }
    })();
    return () => { active = false; };
  }, []);

  const selectedLesson = useMemo<LessonLibraryItem | null>(() => {
    if (!library.selectedLessonId) return null;
    return library.items.find((item) => item.lessonId === library.selectedLessonId) ?? null;
  }, [library]);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    setUploadState({ kind: "uploading", filename: file.name });
    try {
      const formData = new FormData();
      formData.append("file", file);
      const data = await uploadLesson(formData);
      const now = new Date().toISOString();
      const item: LessonLibraryItem = {
        lessonId: data.lesson_id,
        title: data.topic,
        subtitle: `${data.subject} · ${data.grade}`,
        source: "remote",
        status: "uploaded",
        createdAt: now,
        updatedAt: now,
        subject: data.subject,
        grade: data.grade,
        topic: data.topic,
        objectives: data.objectives,
        key_points: data.key_points,
        difficult_points: data.difficult_points,
      };
      setLibrary((prev) => ({
        items: [item, ...prev.items.filter((i) => i.lessonId !== item.lessonId)],
        selectedLessonId: item.lessonId,
      }));
      setUploadState({ kind: "idle" });
    } catch (err) {
      setUploadState({
        kind: "error",
        message: err instanceof Error ? err.message : "上传失败",
      });
    }
  };

  const handleSelectExisting = (lessonId: string) => {
    setLibrary((prev) => ({ ...prev, selectedLessonId: lessonId }));
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragOver(false);
    if (uploadState.kind === "uploading") return;
    void handleFiles(event.dataTransfer.files);
  };

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    void handleFiles(event.target.files);
    // reset 让同名文件能再次触发 change
    event.target.value = "";
  };

  const goNext = () => {
    if (!selectedLesson) return;
    router.push(`/setup/personas?lesson_id=${encodeURIComponent(selectedLesson.lessonId)}`);
  };

  return (
    <main className="relative overflow-hidden px-6 py-10 sm:px-10 lg:px-12">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_right,_rgba(59,130,246,0.12),_transparent_30%),linear-gradient(180deg,_rgba(248,250,252,1),_rgba(241,245,249,0.9))]" />

      <section className="mx-auto w-full max-w-5xl">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold tracking-[0.32em] text-sky-700 uppercase">
            Step 1 / 教案
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
            上传一份教案，开启答疑陪练。
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
            支持 PDF / Markdown / 纯文本。上传后系统会用 LLM 抽取学科、年级、教学目标、重点与难点；通常需要 5-15 秒。
          </p>
        </div>

        {/* 上传区 */}
        <div className="mt-10">
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            className={`flex min-h-[180px] cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed bg-white/70 px-8 py-10 text-center transition ${
              dragOver
                ? "border-sky-500 bg-sky-50/80"
                : uploadState.kind === "uploading"
                  ? "border-slate-300 bg-slate-100"
                  : "border-slate-300 hover:border-sky-400 hover:bg-sky-50/40"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED}
              className="hidden"
              onChange={handleInputChange}
            />
            {uploadState.kind === "uploading" ? (
              <>
                <p className="text-base font-medium text-slate-700">
                  正在解析 <span className="font-semibold text-sky-700">{uploadState.filename}</span>…
                </p>
                <p className="mt-2 text-sm text-slate-500">LLM 抽取中（5-15 秒）；请勿关闭页面。</p>
                <div className="mt-5 h-1.5 w-64 overflow-hidden rounded-full bg-slate-200">
                  <div className="h-full w-1/2 animate-pulse rounded-full bg-sky-500" />
                </div>
              </>
            ) : (
              <>
                <p className="text-base font-medium text-slate-800">
                  拖拽文件到此处，或点击选择
                </p>
                <p className="mt-2 text-sm text-slate-500">支持 .pdf .md .markdown .txt（≤ 10 MB 建议）</p>
              </>
            )}
          </div>
          {uploadState.kind === "error" && (
            <p className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              ⚠ {uploadState.message}
            </p>
          )}
        </div>

        {/* 当前选中的 lesson 卡片 */}
        {selectedLesson && (
          <div className="mt-10 rounded-3xl border border-emerald-200 bg-emerald-50/60 p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold tracking-[0.24em] text-emerald-700 uppercase">
                  已选中
                </p>
                <h2 className="mt-1 text-xl font-semibold text-slate-900">
                  {selectedLesson.title || "未命名课题"}
                </h2>
                <p className="mt-1 text-sm text-slate-600">
                  {selectedLesson.subtitle ?? "—"}
                </p>
              </div>
              <button
                type="button"
                onClick={goNext}
                className="inline-flex shrink-0 items-center justify-center rounded-full bg-slate-950 px-6 py-2.5 text-sm font-semibold text-white shadow-md shadow-slate-950/20 transition hover:-translate-y-0.5 hover:bg-slate-800"
              >
                下一步：选学生 →
              </button>
            </div>

            <div className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
              <MetaBlock title="教学目标" items={selectedLesson.objectives ?? []} />
              <MetaBlock title="教学重点" items={selectedLesson.key_points ?? []} />
              {(selectedLesson.difficult_points ?? []).length > 0 && (
                <MetaBlock
                  title="教学难点"
                  items={selectedLesson.difficult_points ?? []}
                  className="sm:col-span-2"
                />
              )}
            </div>
          </div>
        )}

        {/* 历史教案 */}
        {library.items.length > 0 && (
          <div className="mt-10">
            <h3 className="text-sm font-semibold tracking-[0.2em] text-slate-700 uppercase">
              历史教案
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              已上传的教案可直接复用，无需重新解析。
            </p>
            <ul className="mt-4 grid gap-3 sm:grid-cols-2">
              {library.items.map((item) => {
                const isSelected = item.lessonId === library.selectedLessonId;
                return (
                  <li key={item.lessonId}>
                    <button
                      type="button"
                      onClick={() => handleSelectExisting(item.lessonId)}
                      className={`flex w-full flex-col items-start rounded-2xl border bg-white px-5 py-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${
                        isSelected
                          ? "border-emerald-400 ring-2 ring-emerald-200"
                          : "border-slate-200 hover:border-sky-400"
                      }`}
                    >
                      <p className="text-base font-semibold text-slate-900">
                        {item.title || "未命名课题"}
                      </p>
                      <p className="mt-1 text-sm text-slate-500">
                        {item.subtitle ?? "—"}
                      </p>
                      <p className="mt-2 font-mono text-xs text-slate-400">
                        {item.lessonId}
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        <div className="mt-10 flex items-center gap-4 text-sm text-slate-500">
          <Link href="/" className="hover:text-slate-900">
            ← 回首页
          </Link>
        </div>
      </section>
    </main>
  );
}

function MetaBlock({
  title,
  items,
  className,
}: {
  title: string;
  items: string[];
  className?: string;
}) {
  return (
    <div className={className}>
      <p className="text-xs font-semibold tracking-[0.2em] text-slate-500 uppercase">
        {title}
      </p>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-slate-400">—</p>
      ) : (
        <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
          {items.map((item, idx) => (
            <li key={idx} className="leading-snug">
              <span className="mr-2 text-slate-400">•</span>
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
