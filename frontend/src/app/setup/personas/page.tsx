"use client";

/**
 * #B4 Step 2: 学生选择 + 创建 session。
 *
 * 进入条件：URL ?lesson_id=...（由 /setup 上一步带上来）
 * 流程：
 * - GET /api/lessons/{id}/recommended-personas 拿默认推荐
 * - 卡片网格展示推荐学生（可勾选 / 取消）
 * - 下方"添加更多"区：GET /api/personas?stage_id=... 列同学段其它人设
 * - "开始陪练" → POST /api/qa-sessions → router.push(`/qa/${session_id}`)
 *
 * 状态：纯本地 useState；不依赖 SetupProvider。
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { fetchPersonasByStage } from "@/lib/api/setup";
import { createQASession, fetchRecommendedPersonas } from "@/lib/api/qa";
import type { Persona } from "@/types/persona";
import type { RecommendedPersonasData } from "@/types/qa";

type LoadState = "loading" | "ready" | "error";


export default function SetupPersonasPage() {
  // Next 14 要求 useSearchParams 必须在 Suspense 边界内才能 prerender
  return (
    <Suspense
      fallback={
        <main className="px-6 py-12 text-center text-sm text-slate-500">
          加载中…
        </main>
      }
    >
      <SetupPersonasInner />
    </Suspense>
  );
}

function SetupPersonasInner() {
  const router = useRouter();
  const params = useSearchParams();
  const lessonId = params.get("lesson_id");

  const [recommend, setRecommend] = useState<RecommendedPersonasData | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMsg, setErrorMsg] = useState("");

  /** 用户最终选定的 persona id 集合（包含勾选 + 手动加的）。 */
  const [selected, setSelected] = useState<Set<string>>(new Set());
  /** 同学段全部 persona（点"添加更多"时按需加载）。 */
  const [pool, setPool] = useState<Persona[]>([]);
  const [poolLoading, setPoolLoading] = useState(false);
  const [showPool, setShowPool] = useState(false);

  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  // 加载推荐
  useEffect(() => {
    if (!lessonId) {
      setLoadState("error");
      setErrorMsg("URL 缺少 lesson_id，请回到上一步重新选择教案。");
      return;
    }
    let active = true;
    setLoadState("loading");
    setErrorMsg("");

    void (async () => {
      try {
        const data = await fetchRecommendedPersonas(lessonId, 4);
        if (!active) return;
        setRecommend(data);
        setSelected(new Set(data.persona_ids));
        setLoadState("ready");
      } catch (err) {
        if (!active) return;
        setLoadState("error");
        setErrorMsg(err instanceof Error ? err.message : "加载推荐学生失败");
      }
    })();

    return () => {
      active = false;
    };
  }, [lessonId]);

  // 同学段全 persona 池
  const loadPool = useCallback(async () => {
    if (!recommend) return;
    setPoolLoading(true);
    try {
      const data = await fetchPersonasByStage(recommend.stage_id);
      setPool(data);
    } catch (err) {
      console.error("加载同学段 persona 池失败", err);
    } finally {
      setPoolLoading(false);
    }
  }, [recommend]);

  useEffect(() => {
    if (showPool && pool.length === 0 && !poolLoading) {
      void loadPool();
    }
  }, [showPool, pool.length, poolLoading, loadPool]);

  const toggle = (personaId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(personaId)) next.delete(personaId);
      else next.add(personaId);
      return next;
    });
  };

  const recommendedSet = useMemo(
    () => new Set(recommend?.persona_ids ?? []),
    [recommend],
  );

  const additionalPool = useMemo(
    () => pool.filter((p) => !recommendedSet.has(p.id)),
    [pool, recommendedSet],
  );

  const startSession = async () => {
    if (!lessonId || selected.size === 0) return;
    setCreating(true);
    setCreateError("");
    try {
      const data = await createQASession({
        lesson_id: lessonId,
        persona_ids: Array.from(selected),
      });
      router.push(`/qa/${encodeURIComponent(data.session_id)}`);
    } catch (err) {
      setCreating(false);
      setCreateError(err instanceof Error ? err.message : "创建陪练失败");
    }
  };

  return (
    <main className="relative overflow-hidden px-6 py-10 sm:px-10 lg:px-12">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_right,_rgba(16,185,129,0.12),_transparent_30%),linear-gradient(180deg,_rgba(248,250,252,1),_rgba(241,245,249,0.9))]" />

      <section className="mx-auto w-full max-w-6xl">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold tracking-[0.32em] text-emerald-700 uppercase">
            Step 2 / 学生
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
            选几个会向你提问的学生。
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
            系统已根据教案学段挑了一组推荐学生，你可以增减。
          </p>
        </div>

        {loadState === "loading" && (
          <p className="mt-12 text-sm text-slate-500">正在加载推荐学生…</p>
        )}

        {loadState === "error" && (
          <div className="mt-12 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">
            <p>⚠ {errorMsg}</p>
            <Link
              href="/setup"
              className="mt-3 inline-flex text-sm font-medium text-rose-700 underline-offset-2 hover:underline"
            >
              ← 回到上一步
            </Link>
          </div>
        )}

        {loadState === "ready" && recommend && (
          <>
            {/* 教案信息条 */}
            <div className="mt-8 rounded-2xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-700 shadow-sm">
              <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
                <span className="font-semibold text-slate-900">{recommend.topic}</span>
                <span className="text-slate-500">
                  {recommend.subject} · {recommend.grade} · {recommend.stage_name}
                </span>
                <span className="ml-auto font-mono text-xs text-slate-400">
                  {recommend.lesson_id}
                </span>
              </div>
            </div>

            {/* 推荐学生网格 */}
            <h2 className="mt-10 text-sm font-semibold tracking-[0.2em] text-slate-700 uppercase">
              推荐学生（{recommend.students.length}）
            </h2>
            <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {recommend.students.map((p) => (
                <PersonaCard
                  key={p.id}
                  persona={p}
                  selected={selected.has(p.id)}
                  onToggle={() => toggle(p.id)}
                />
              ))}
            </ul>

            {/* 添加更多 */}
            <div className="mt-10">
              <button
                type="button"
                onClick={() => setShowPool((v) => !v)}
                className="text-sm font-medium text-sky-700 hover:text-sky-900"
              >
                {showPool ? "收起" : "+ 添加同学段其它学生"}
              </button>
              {showPool && (
                <div className="mt-4">
                  {poolLoading ? (
                    <p className="text-sm text-slate-500">正在加载…</p>
                  ) : additionalPool.length === 0 ? (
                    <p className="text-sm text-slate-500">同学段没有其它学生可选。</p>
                  ) : (
                    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                      {additionalPool.map((p) => (
                        <PersonaCard
                          key={p.id}
                          persona={p}
                          selected={selected.has(p.id)}
                          onToggle={() => toggle(p.id)}
                        />
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>

            {/* 底部操作栏 */}
            <div className="mt-12 flex flex-col gap-5 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:flex-row sm:items-center sm:justify-between">
              <Link
                href="/setup"
                className="text-sm font-medium text-slate-600 hover:text-slate-900"
              >
                ← 回到上一步（换教案）
              </Link>
              <button
                type="button"
                disabled={selected.size === 0 || creating}
                onClick={startSession}
                className="inline-flex items-center justify-center rounded-full bg-emerald-600 px-7 py-3 text-base font-semibold text-white shadow-md shadow-emerald-600/20 transition hover:-translate-y-0.5 hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none disabled:hover:translate-y-0"
              >
                {creating ? "正在生成问题…" : "开始陪练 →"}
              </button>
            </div>

            {createError && (
              <p className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                ⚠ {createError}
              </p>
            )}
          </>
        )}
      </section>
    </main>
  );
}

interface PersonaLike {
  id: string;
  name: string;
  gender: string;
  grade: string;
  age: number;
  subject_level: string;
  summary: string;
}

function PersonaCard({
  persona,
  selected,
  onToggle,
}: {
  persona: PersonaLike;
  selected: boolean;
  onToggle: () => void;
}) {
  const initial = persona.name.charAt(0);
  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        className={`group flex h-full w-full flex-col items-start rounded-2xl border bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${
          selected
            ? "border-emerald-500 ring-2 ring-emerald-200"
            : "border-slate-200 hover:border-sky-400"
        }`}
      >
        <div className="flex w-full items-center gap-3">
          <div
            className={`flex size-11 items-center justify-center rounded-full text-base font-semibold ${
              selected ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"
            }`}
          >
            {initial}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-semibold text-slate-900">
              {persona.name}
            </p>
            <p className="text-xs text-slate-500">
              {persona.grade} · {persona.gender || "—"} · {persona.subject_level}
            </p>
          </div>
          <div
            className={`size-5 shrink-0 rounded-full border-2 transition ${
              selected
                ? "border-emerald-500 bg-emerald-500"
                : "border-slate-300 group-hover:border-slate-400"
            }`}
            aria-hidden
          >
            {selected && (
              <svg viewBox="0 0 20 20" fill="currentColor" className="size-full text-white">
                <path
                  fillRule="evenodd"
                  d="M16.7 5.3a1 1 0 010 1.4l-7.5 7.5a1 1 0 01-1.4 0l-3.5-3.5a1 1 0 111.4-1.4l2.8 2.8 6.8-6.8a1 1 0 011.4 0z"
                  clipRule="evenodd"
                />
              </svg>
            )}
          </div>
        </div>
        <p className="mt-3 text-sm leading-snug text-slate-600">
          {persona.summary || "—"}
        </p>
      </button>
    </li>
  );
}
