"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { fetchPersonasByStage, fetchStages, uploadLesson } from "@/lib/api/setup";
import type { Persona } from "@/types/persona";
import type { Stage } from "@/types/stage";
import type { LessonLibraryItem } from "@/types/setup";
import { useSetup } from "@/components/setup/setup-provider";

const emptyLessonHint = "当前本地教案库为空，先上传一份教案再开始配置。";

type LoadState = "idle" | "loading" | "ready" | "empty" | "error";

function toLessonLibraryItem(payload: Awaited<ReturnType<typeof uploadLesson>>): LessonLibraryItem {
  const now = new Date().toISOString();

  return {
    lessonId: payload.lesson_id,
    title: payload.topic,
    subtitle: `${payload.subject} · ${payload.grade}`,
    source: "remote",
    status: "uploaded",
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

export function SetupConfigClient() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const { draft, updateDraft, library, addLesson, selectLesson } = useSetup();

  const selectedLessonId = draft.selectedLessonId ?? library.selectedLessonId;
  const selectedStageId = draft.selectedStageId;

  const [stages, setStages] = useState<Stage[]>([]);
  const [stageState, setStageState] = useState<LoadState>("loading");
  const [stageError, setStageError] = useState("");
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [personaState, setPersonaState] = useState<LoadState>("idle");
  const [personaError, setPersonaError] = useState("");
  const [uploadState, setUploadState] = useState<LoadState>("idle");
  const [uploadMessage, setUploadMessage] = useState("可从本地暂存继续，也可以直接上传新教案。");

  useEffect(() => {
    let active = true;

    const loadStages = async () => {
      setStageState("loading");
      setStageError("");

      try {
        const data = await fetchStages();
        if (!active) return;
        setStages(data);
        setStageState(data.length > 0 ? "ready" : "empty");
      } catch (error) {
        if (!active) return;
        setStages([]);
        setStageState("error");
        setStageError(error instanceof Error ? error.message : "加载学段失败");
      }
    };

    void loadStages();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedStageId) {
      setPersonas([]);
      setPersonaState("idle");
      setPersonaError("");
      return;
    }

    let active = true;

    const loadPersonas = async () => {
      setPersonaState("loading");
      setPersonaError("");

      try {
        const data = await fetchPersonasByStage(selectedStageId);
        if (!active) return;
        setPersonas(data);
        setPersonaState(data.length > 0 ? "ready" : "empty");
      } catch (error) {
        if (!active) return;
        setPersonas([]);
        setPersonaState("error");
        setPersonaError(error instanceof Error ? error.message : "加载学生失败");
      }
    };

    void loadPersonas();
    return () => {
      active = false;
    };
  }, [selectedStageId]);

  const selectedStage = useMemo(
    () => stages.find((stage) => stage.id === selectedStageId) ?? null,
    [stages, selectedStageId],
  );
  const selectedLesson = useMemo(
    () => library.items.find((lesson) => lesson.lessonId === selectedLessonId) ?? null,
    [library.items, selectedLessonId],
  );
  const selectedPersonas = useMemo(
    () => personas.filter((persona) => draft.selectedPersonaIds.includes(persona.id)),
    [draft.selectedPersonaIds, personas],
  );

  const handleChooseLesson = (lesson: LessonLibraryItem) => {
    selectLesson(lesson.lessonId);
    updateDraft({ selectedLessonId: lesson.lessonId });
  };

  const handleTogglePersona = (personaId: string) => {
    const next = draft.selectedPersonaIds.includes(personaId)
      ? draft.selectedPersonaIds.filter((id) => id !== personaId)
      : [...draft.selectedPersonaIds, personaId];

    updateDraft({ selectedPersonaIds: next });
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";

    if (!file) return;

    setUploadState("loading");
    setUploadMessage(`正在上传 ${file.name} ...`);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", file.name.replace(/\.[^.]+$/, ""));

      const payload = await uploadLesson(formData);
      const lessonItem = toLessonLibraryItem(payload);

      addLesson(lessonItem);
      selectLesson(lessonItem.lessonId);
      updateDraft({ selectedLessonId: lessonItem.lessonId });

      setUploadState("ready");
      setUploadMessage(`已写入本地教案库：${lessonItem.title ?? lessonItem.lessonId}`);
    } catch (error) {
      setUploadState("error");
      setUploadMessage(error instanceof Error ? error.message : "上传失败");
    }
  };

  const stageLabel = selectedStage?.name ?? selectedStageId ?? "尚未选择学段";
  const lessonLabel = selectedLesson?.title ?? selectedLesson?.topic ?? selectedLessonId ?? "尚未选择教案";
  const personaCount = draft.selectedPersonaIds.length;

  return (
    <main className="relative overflow-hidden px-6 py-10 sm:px-10 lg:px-12">
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,_rgba(14,165,233,0.12),_transparent_30%),linear-gradient(180deg,_rgba(248,250,252,1),_rgba(241,245,249,0.92))]" />

      <section className="mx-auto w-full max-w-6xl">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold tracking-[0.32em] text-sky-700 uppercase">Step 2 / 配置</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
            教案与学生同页配置。
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
            教案区读取本地暂存，学生区读取真实接口，底部摘要直接来自 setup draft。
          </p>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-sm backdrop-blur-sm sm:p-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-slate-500">教案库</p>
                <h2 className="mt-1 text-2xl font-semibold text-slate-950">本地暂存 + 真实上传</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  先从本地教案库中选一个，再通过上传接口补充新的教案文件。
                </p>
              </div>
              <div className="flex flex-col items-end gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-950 transition hover:border-slate-400 hover:bg-slate-50"
                >
                  上传教案
                </button>
                <p className="text-xs text-slate-500">成功后会写入本地库</p>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept=".pdf,.md,.txt,.doc,.docx"
                  onChange={handleUpload}
                />
              </div>
            </div>

            <div className="mt-6 grid gap-4">
              {library.items.length > 0 ? (
                library.items.map((item) => {
                  const active = item.lessonId === selectedLessonId;

                  return (
                    <button
                      key={item.lessonId}
                      type="button"
                      onClick={() => handleChooseLesson(item)}
                      className={`rounded-3xl border p-5 text-left transition ${active ? "border-slate-950 bg-slate-950 text-white shadow-lg shadow-slate-950/15" : "border-slate-200 bg-slate-50 text-slate-900 hover:border-slate-300 hover:bg-white"}`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className={`text-xs font-medium tracking-[0.2em] uppercase ${active ? "text-slate-300" : "text-slate-500"}`}>
                            {item.subject ?? item.source}
                          </p>
                          <h3 className="mt-2 text-lg font-semibold">
                            {item.title ?? item.topic ?? item.lessonId}
                          </h3>
                        </div>
                        <span className={`rounded-full px-3 py-1 text-xs font-medium ${active ? "bg-white/15 text-white" : "bg-slate-200 text-slate-700"}`}>
                          {active ? "已选中" : "点击选择"}
                        </span>
                      </div>
                      <p className={`mt-3 text-sm leading-6 ${active ? "text-slate-200" : "text-slate-600"}`}>
                        {item.subtitle ?? item.topic ?? "已写入本地暂存，可直接复用。"}
                      </p>
                      <div className={`mt-4 flex flex-wrap gap-2 text-xs ${active ? "text-slate-300" : "text-slate-500"}`}>
                        {item.grade ? <span>年级：{item.grade}</span> : null}
                        <span>{item.status}</span>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm leading-6 text-slate-600">
                  <p className="font-medium text-slate-900">暂无本地教案</p>
                  <p className="mt-2">{emptyLessonHint}</p>
                </div>
              )}
            </div>

            <div className={`mt-6 rounded-2xl p-4 text-sm leading-6 ${uploadState === "error" ? "bg-rose-50 text-rose-700" : "bg-slate-50 text-slate-600"}`}>
              <p className="font-medium text-slate-900">上传状态</p>
              <p className="mt-1">{uploadMessage}</p>
            </div>
          </section>

          <section className="space-y-6">
            <div className="rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-sm backdrop-blur-sm sm:p-8">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-slate-500">学生选择</p>
                  <h2 className="mt-1 text-2xl font-semibold text-slate-950">按学段加载真实人设</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {selectedStageId
                      ? stageState === "loading"
                        ? "学段信息同步中…"
                        : stageState === "error"
                          ? stageError
                          : stageLabel
                      : "未选择学段"}
                  </p>
                </div>
                <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-700">
                  {personaCount} 位已选
                </span>
              </div>

              {!selectedStageId ? (
                <div className="mt-6 rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm leading-6 text-slate-600">
                  <p className="font-medium text-slate-900">先选择学段</p>
                  <p className="mt-2">学生列表会根据当前 selectedStageId 调用 `/api/personas?stage_id=...`。</p>
                  <Link
                    href="/setup/stage"
                    className="mt-4 inline-flex items-center justify-center rounded-full bg-slate-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
                  >
                    返回学段页
                  </Link>
                </div>
              ) : personaState === "loading" ? (
                <div className="mt-6 grid gap-4">
                  {[0, 1, 2].map((item) => (
                    <div key={item} className="animate-pulse rounded-3xl border border-slate-200 bg-slate-50 p-5">
                      <div className="h-4 w-20 rounded-full bg-slate-200" />
                      <div className="mt-4 h-6 w-1/2 rounded-full bg-slate-200" />
                      <div className="mt-3 h-4 w-full rounded-full bg-slate-200" />
                    </div>
                  ))}
                </div>
              ) : personaState === "error" ? (
                <div className="mt-6 rounded-3xl border border-rose-200 bg-rose-50 p-6 text-sm leading-6 text-rose-700">
                  <p className="font-semibold">学生加载失败</p>
                  <p className="mt-2">{personaError}</p>
                </div>
              ) : personaState === "empty" ? (
                <div className="mt-6 rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm leading-6 text-slate-600">
                  <p className="font-medium text-slate-900">暂无可用学生</p>
                  <p className="mt-2">当前学段没有返回人设数据。</p>
                </div>
              ) : (
                <div className="mt-6 grid gap-4">
                  {personas.map((persona) => {
                    const active = draft.selectedPersonaIds.includes(persona.id);

                    return (
                      <button
                        key={persona.id}
                        type="button"
                        onClick={() => handleTogglePersona(persona.id)}
                        className={`rounded-3xl border p-5 text-left transition ${active ? "border-sky-500 bg-sky-50 text-slate-950" : "border-slate-200 bg-slate-50 text-slate-900 hover:border-slate-300 hover:bg-white"}`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <h3 className="text-lg font-semibold">{persona.name}</h3>
                          <span className={`rounded-full px-3 py-1 text-xs font-medium ${active ? "bg-sky-600 text-white" : "bg-slate-200 text-slate-700"}`}>
                            {active ? "已选" : "选择"}
                          </span>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-slate-600">{persona.summary ?? persona.description ?? "暂无摘要"}</p>
                        <p className="mt-3 text-xs text-slate-500">{persona.stage_id ?? selectedStageId}</p>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="rounded-3xl border border-slate-200 bg-slate-950 p-6 text-white shadow-lg shadow-slate-950/10 sm:p-8">
              <p className="text-sm font-medium text-slate-300">配置摘要</p>
              <div className="mt-4 grid gap-3 text-sm leading-6 text-slate-200">
                <p><span className="text-slate-400">学段：</span>{stageLabel}</p>
                <p><span className="text-slate-400">教案：</span>{lessonLabel}</p>
                <p><span className="text-slate-400">学生：</span>{personaCount > 0 ? selectedPersonas.map((item) => item.name).join("、") : "尚未选择学生"}</p>
              </div>
              <p className="mt-4 text-sm leading-6 text-slate-300">
                当前摘要直接读取本地 draft；课堂实时互动尚未接后端。
              </p>
              <Link
                href="/classroom/demo"
                className="mt-6 inline-flex w-full items-center justify-center rounded-2xl bg-white px-4 py-3 text-sm font-medium text-slate-950 transition hover:bg-slate-100"
              >
                进入课堂演示
              </Link>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}
