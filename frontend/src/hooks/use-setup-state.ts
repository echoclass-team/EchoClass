"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { LessonLibraryItem, LessonLibraryState, SetupDraft } from "@/types/setup";
import { DEFAULT_SETUP_DRAFT } from "@/types/setup";
import { getSetupDraft, setSetupDraft } from "@/lib/setup-storage";
import { fetchLessons, type LessonListItem } from "@/lib/api/setup";

export function useSetupDraftState() {
  const [draft, setDraftState] = useState<SetupDraft>(DEFAULT_SETUP_DRAFT);

  useEffect(() => setDraftState(getSetupDraft()), []);

  const updateDraft = useCallback((patch: Partial<SetupDraft>) => {
    setDraftState((current) => {
      const next = { ...current, ...patch };
      setSetupDraft(next);
      return next;
    });
  }, []);

  return useMemo(() => ({ draft, updateDraft }), [draft, updateDraft]);
}

function dbRowToItem(row: LessonListItem): LessonLibraryItem {
  return {
    lessonId: row.lesson_id,
    title: row.title || row.topic,
    subtitle: `${row.subject} · ${row.grade}`,
    subject: row.subject,
    grade: row.grade,
    topic: row.topic,
    source: "local",
    status: "ready",
    createdAt: row.created_at,
    objectives: row.objectives,
    key_points: row.key_points,
    difficult_points: row.difficult_points,
  };
}

export function useLessonLibraryState() {
  const [library, setLibraryState] = useState<LessonLibraryState>({ items: [], selectedLessonId: null });

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const rows = await fetchLessons();
        if (!active) return;
        const items = rows.map(dbRowToItem);
        setLibraryState((prev) => ({ items, selectedLessonId: prev.selectedLessonId }));
      } catch {
        // 未登录 / 网络失败时静默，保持空列表
      }
    })();
    return () => { active = false; };
  }, []);

  const addLesson = useCallback((item: LessonLibraryItem) => {
    setLibraryState((prev) => {
      const items = [item, ...prev.items.filter((i) => i.lessonId !== item.lessonId)];
      return { ...prev, items };
    });
  }, []);

  const removeLesson = useCallback((lessonId: string) => {
    setLibraryState((prev) => {
      const items = prev.items.filter((i) => i.lessonId !== lessonId);
      const selectedLessonId = prev.selectedLessonId === lessonId ? null : prev.selectedLessonId;
      return { items, selectedLessonId };
    });
  }, []);

  const selectLesson = useCallback((lessonId: string | null) => {
    setLibraryState((prev) => ({ ...prev, selectedLessonId: lessonId }));
  }, []);

  const replaceLibrary = useCallback((state: LessonLibraryState) => {
    setLibraryState(state);
  }, []);

  return useMemo(() => ({ library, addLesson, removeLesson, selectLesson, replaceLibrary }), [library, addLesson, removeLesson, selectLesson, replaceLibrary]);
}
