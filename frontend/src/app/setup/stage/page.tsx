"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { Stage } from "@/types/stage";
import { fetchStages } from "@/lib/api/setup";
import { useSetup } from "@/components/setup/setup-provider";

type LoadState = "loading" | "ready" | "empty" | "error";

export default function StageSetupPage() {
  const { draft, updateDraft } = useSetup();
  const [stages, setStages] = useState<Stage[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);

  const selectedStage = useMemo(() => stages.find((stage) => stage.id === selectedStageId) ?? null, [stages, selectedStageId]);

  useEffect(() => {
    if (draft.selectedStageId && draft.selectedStageId !== selectedStageId) {
      setSelectedStageId(draft.selectedStageId);
    }
  }, [draft.selectedStageId, selectedStageId]);

  useEffect(() => {
    let active = true;

    const load = async () => {
      setLoadState("loading");
      setErrorMessage("");

      try {
        const data = await fetchStages();
        if (!active) return;
        setStages(data);
        setLoadState(data.length > 0 ? "ready" : "empty");
      } catch (error) {
        if (!active) return;
        setStages([]);
        setLoadState("error");
        setErrorMessage(error instanceof Error ? error.message : "加载学段失败");
      }
    };

    void load();
    return () => {
      active = false;
    };
  }, []);

  const handleSelectStage = (stageId: string) => {
    setSelectedStageId(stageId);
    updateDraft({ selectedStageId: stageId, selectedPersonaIds: [] });
  };

  const statusCopy =
    loadState === "loading"
      ? "正在从 /api/stages 读取学段列表。"
      : loadState === "error"
        ? errorMessage || "学段加载失败，请重试。"
        : loadState === "empty"
          ? "接口返回为空，当前没有可选学段。"
          : selectedStage
            ? `已选中 ${selectedStage.name}，可以继续进入配置。`
            : "请选择一个学段，系统会把它写入 setup draft。";

  return (
    <main className="relative overflow-hidden px-6 py-10 sm:px-10 lg:px-12">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_right,_rgba(59,130,246,0.12),_transparent_30%),linear-gradient(180deg,_rgba(248,250,252,1),_rgba(241,245,249,0.9))]" />

      <section className="mx-auto w-full max-w-6xl">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold tracking-[0.32em] text-sky-700 uppercase">Step 1 / 学段</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
            先选一个学段，再继续配置。
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
            学段列表来自真实接口，选中后会写入本地 setup draft，供后续教案和学生配置复用。
          </p>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <section className="flex h-full flex-col rounded-3xl border border-slate-200 bg-white/85 p-6 shadow-sm backdrop-blur-sm sm:p-8">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-slate-500">学段卡片</p>
                <h2 className="mt-1 text-2xl font-semibold text-slate-950">真实接口 / 可选状态</h2>
              </div>
            </div>

            <div className="flex-1">
              {loadState === "loading" ? (
                <div className="mt-6 grid gap-4 md:grid-cols-2">
                  {[0, 1, 2, 3].map((item) => (
                    <div key={item} className="animate-pulse rounded-3xl border border-slate-200 bg-slate-50 p-5">
                      <div className="h-4 w-20 rounded-full bg-slate-200" />
                      <div className="mt-4 h-6 w-2/3 rounded-full bg-slate-200" />
                      <div className="mt-3 h-4 w-full rounded-full bg-slate-200" />
                      <div className="mt-2 h-4 w-5/6 rounded-full bg-slate-200" />
                    </div>
                  ))}
                </div>
              ) : loadState === "error" ? (
                <div className="mt-6 rounded-3xl border border-rose-200 bg-rose-50 p-6 text-sm leading-6 text-rose-700">
                  <p className="font-semibold">学段加载失败</p>
                  <p className="mt-2">{errorMessage}</p>
                  <button
                    type="button"
                    onClick={() => window.location.reload()}
                    className="mt-4 rounded-full bg-rose-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-700"
                  >
                    重新加载
                  </button>
                </div>
              ) : loadState === "empty" ? (
                <div className="mt-6 rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm leading-6 text-slate-600">
                  <p className="font-medium text-slate-900">暂无可选学段</p>
                  <p className="mt-2">接口返回为空，当前流程暂时无法继续。</p>
                </div>
              ) : (
                <div className="mt-6 grid gap-4 md:grid-cols-2">
                  {stages.map((stage) => {
                    const active = stage.id === selectedStageId;

                    return (
                      <button
                        key={stage.id}
                        type="button"
                        onClick={() => handleSelectStage(stage.id)}
                        className={`rounded-3xl border p-5 text-left transition ${active ? "border-slate-950 bg-slate-950 text-white shadow-lg shadow-slate-950/15" : "border-slate-200 bg-slate-50 text-slate-900 hover:border-slate-300 hover:bg-white"}`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <h3 className="text-xl font-semibold">{stage.name}</h3>
                          <span className={`rounded-full px-3 py-1 text-xs font-medium ${active ? "bg-white/15 text-white" : "bg-slate-200 text-slate-700"}`}>
                            {active ? "已选中" : "点击选择"}
                          </span>
                        </div>
                        <p className={`mt-3 text-sm leading-6 ${active ? "text-slate-200" : "text-slate-600"}`}>
                          {stage.description ?? "暂无说明"}
                        </p>
                        <div className={`mt-4 flex flex-wrap gap-2 text-xs ${active ? "text-slate-300" : "text-slate-500"}`}>
                          {stage.grade_range ? <span>年级：{stage.grade_range}</span> : null}
                          {stage.age_range ? <span>年龄：{stage.age_range}</span> : null}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="mt-6 flex justify-end">
              <Link
                href="/setup/config"
                className="rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-400 hover:bg-slate-50"
              >
                下一步：进入配置
              </Link>
            </div>
          </section>

          <aside className="space-y-4">
            <section className="rounded-3xl border border-slate-200 bg-white/85 p-6 shadow-sm backdrop-blur-sm sm:p-8">
              <p className="text-sm font-medium text-slate-500">当前状态</p>
              <h2 className="mt-1 text-2xl font-semibold text-slate-950">写入 setup draft</h2>
              <div className="mt-5 grid gap-3">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                  {statusCopy}
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                  <p className="font-medium text-slate-900">当前选中</p>
                  <p className="mt-1">{selectedStage ? `${selectedStage.name} · ${selectedStage.id}` : "尚未选择学段"}</p>
                </div>
              </div>
            </section>

            <section className="rounded-3xl border border-sky-200 bg-sky-50 p-6 text-sm leading-6 text-slate-700 shadow-sm sm:p-8">
              <p className="font-semibold text-slate-950">下一步</p>
              <p className="mt-2">选中学段后进入配置页，教案与学生会在同一页完成。</p>
            </section>
          </aside>
        </div>
      </section>
    </main>
  );
}
