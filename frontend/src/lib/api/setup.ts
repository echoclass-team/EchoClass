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

export interface LessonListItem {
  lesson_id: string;
  title: string;
  subject: string;
  grade: string;
  topic: string;
  filename: string;
  created_at: string;
  objectives: string[];
  key_points: string[];
  difficult_points: string[];
}

export async function fetchLessons() {
  return unwrap((await apiFetch<LessonListItem[]>("/api/lessons")).data, "Failed to load lessons");
}

export async function fetchLesson(lessonId: string) {
  return unwrap((await apiFetch<LessonRecord>(`/api/lessons/${encodeURIComponent(lessonId)}`)).data, "Failed to load lesson");
}

export async function deleteLesson(lessonId: string) {
  return unwrap(
    (await apiFetch<{ lesson_id: string; deleted: boolean }>(`/api/lessons/${encodeURIComponent(lessonId)}`, { method: "DELETE" })).data,
    "Failed to delete lesson",
  );
}
