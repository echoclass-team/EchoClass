"use client";

import Link from "next/link";

export default function Home() {
  return (
    <main className="relative overflow-hidden px-6 py-10 sm:px-10 lg:px-12">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,_rgba(56,189,248,0.18),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(15,23,42,0.08),_transparent_28%),linear-gradient(180deg,_rgba(248,250,252,1),_rgba(241,245,249,0.8))]" />

      <section className="mx-auto flex min-h-[calc(100vh-6rem)] w-full max-w-5xl flex-col justify-center gap-10">
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
            href="/lessons/manage"
            className="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white px-6 py-3 text-base font-medium text-slate-950 transition hover:border-slate-400 hover:bg-slate-50"
          >
            教案管理
          </Link>
        </div>
      </section>
    </main>
  );
}
