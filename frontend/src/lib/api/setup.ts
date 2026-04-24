import { apiFetch } from "./client";
import type { Stage } from "@/types/stage";
import type { Persona } from "@/types/persona";
import type { LessonRecord, LessonUploadData } from "@/types/lesson";

function unwrap<T>(data: T | null, fallbackMessage: string): T {
  if (data === null) throw new Error(fallbackMessage);
  return data;
}

export async function fetchStages() {
  return unwrap((await apiFetch<Stage[]>("/api/stages")).data, "Failed to load stages");
}

export async function fetchStage(stageId: string) {
  return unwrap((await apiFetch<Stage>(`/api/stages/${encodeURIComponent(stageId)}`)).data, "Failed to load stage");
}

export async function fetchPersonas() {
  return unwrap((await apiFetch<Persona[]>("/api/personas")).data, "Failed to load personas");
}

export async function fetchPersonasByStage(stageId: string) {
  const params = new URLSearchParams({ stage_id: stageId });
  return unwrap((await apiFetch<Persona[]>(`/api/personas?${params.toString()}`)).data, "Failed to load personas");
}

export async function uploadLesson(formData: FormData) {
  return unwrap((await apiFetch<LessonUploadData>("/api/lessons/upload", { method: "POST", body: formData })).data, "Failed to upload lesson");
}

export async function fetchLesson(lessonId: string) {
  return unwrap((await apiFetch<LessonRecord>(`/api/lessons/${encodeURIComponent(lessonId)}`)).data, "Failed to load lesson");
}
