"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getLessonLibrary } from "@/lib/setup-storage";

export default function Home() {
  const [library, setLibrary] = useState(() => getLessonLibrary());

  useEffect(() => {
    setLibrary(getLessonLibrary());
  }, []);

  const previewItems = useMemo(() => library.items.slice(0, 3), [library.items]);

  return (
    <main className="relative overflow-hidden px-6 py-10 sm:px-10 lg:px-12">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.18),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(15,23,42,0.08),_transparent_28%),linear-gradient(180deg,_rgba(248,250,252,1),_rgba(241,245,249,0.8))]" />

      <section className="mx-auto flex min-h-[calc(100vh-6rem)] w-full max-w-6xl flex-col justify-center gap-12">
        <div className="max-w-3xl">
          <p className="mb-4 text-xs font-semibold tracking-[0.32em] text-sky-700 uppercase">
            EchoClass / 演练入口
          </p>
          <h1 className="text-4xl font-semibold tracking-tight text-slate-950 sm:text-5xl lg:text-6xl">
            先开始演练，再补全课堂。
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">
            从学段开始，进入教案与学生配置，再带着真实的本地草稿进入课堂演示页。
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <Link
            href="/setup/stage"
            className="inline-flex items-center justify-center rounded-full bg-slate-950 px-7 py-3 text-base font-medium text-white shadow-lg shadow-slate-950/15 transition hover:-translate-y-0.5 hover:bg-slate-800"
          >
            开始演练
          </Link>
          <Link
            href="/setup/config"
            className="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white px-6 py-3 text-base font-medium text-slate-950 transition hover:border-slate-400 hover:bg-slate-50"
          >
            上传教案
          </Link>
        </div>
      </section>

      <section className="mx-auto mt-8 grid w-full max-w-6xl gap-6 lg:grid-cols-[1.25fr_0.75fr]">
        <article className="rounded-3xl border border-slate-200 bg-white/85 p-6 shadow-sm backdrop-blur-sm sm:p-8">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-slate-500">教案库预览</p>
              <h2 className="mt-1 text-2xl font-semibold text-slate-950">本地暂存优先</h2>
            </div>
            <span className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700">
              {library.items.length} 条记录
            </span>
          </div>

          {previewItems.length > 0 ? (
            <div className="mt-6 grid gap-4 md:grid-cols-3">
              {previewItems.map((lesson) => (
                <div key={lesson.lessonId} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs font-medium tracking-[0.2em] text-slate-500 uppercase">
                    {lesson.subject ?? lesson.source}
                  </p>
                  <h3 className="mt-2 text-base font-semibold text-slate-950">
                    {lesson.title ?? lesson.topic ?? lesson.lessonId}
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {lesson.subtitle ?? lesson.topic ?? "已写入本地暂存，打开配置页即可复用。"}
                  </p>
                  <p className="mt-4 text-xs text-slate-500">{lesson.source === "remote" ? "上传后写入本地库" : "本地暂存"}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm leading-6 text-slate-600">
              <p className="font-medium text-slate-900">当前暂无本地教案</p>
              <p className="mt-2">上传后会先写入本地暂存，再出现在这里。</p>
            </div>
          )}
        </article>

        <aside className="rounded-3xl border border-slate-200 bg-white/85 p-6 shadow-sm backdrop-blur-sm sm:p-8">
          <p className="text-sm font-medium text-slate-500">辅助入口</p>
          <h2 className="mt-1 text-2xl font-semibold text-slate-950">教案上传</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            进入配置页即可上传教案，成功后会写回本地教案库，方便后续课堂演示复用。
          </p>
          <div className="mt-6 rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">
            <p className="font-medium text-slate-900">状态</p>
            <p className="mt-1">{library.items.length > 0 ? "本地暂存已存在可复用教案" : "本地暂存为空，等待第一次上传"}</p>
          </div>
        </aside>
      </section>
    </main>
  );
}
