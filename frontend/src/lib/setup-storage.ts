import type { LessonLibraryItem, LessonLibraryState, SetupDraft } from "@/types/setup";
import { DEFAULT_SETUP_DRAFT } from "@/types/setup";

const DRAFT_KEY = "echoclass.setup.draft";
const LIBRARY_KEY = "echoclass.setup.lessonLibrary";

function readJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(key, JSON.stringify(value));
}

export function getSetupDraft(): SetupDraft {
  return readJson<SetupDraft>(DRAFT_KEY, DEFAULT_SETUP_DRAFT);
}

export function setSetupDraft(draft: SetupDraft) {
  writeJson(DRAFT_KEY, draft);
}

export function clearSetupDraft() {
  setSetupDraft(DEFAULT_SETUP_DRAFT);
}

export function getLessonLibrary(): LessonLibraryState {
  return readJson<LessonLibraryState>(LIBRARY_KEY, { items: [], selectedLessonId: null });
}

export function setLessonLibrary(state: LessonLibraryState) {
  writeJson(LIBRARY_KEY, state);
}

export function upsertLessonLibraryItem(item: LessonLibraryItem) {
  const current = getLessonLibrary();
  const items = current.items.filter((entry) => entry.lessonId !== item.lessonId);
  items.unshift(item);
  const next: LessonLibraryState = { ...current, items };
  setLessonLibrary(next);
  return next;
}

export function removeLessonLibraryItem(lessonId: string) {
  const current = getLessonLibrary();
  const items = current.items.filter((entry) => entry.lessonId !== lessonId);
  const selectedLessonId =
    current.selectedLessonId === lessonId ? null : current.selectedLessonId;
  const next: LessonLibraryState = { items, selectedLessonId };
  setLessonLibrary(next);
  return next;
}

export function selectLessonInLibrary(lessonId: string | null) {
  const current = getLessonLibrary();
  const next: LessonLibraryState = { ...current, selectedLessonId: lessonId };
  setLessonLibrary(next);
  return next;
}
