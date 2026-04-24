"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { LessonLibraryItem, LessonLibraryState, SetupDraft } from "@/types/setup";
import { DEFAULT_SETUP_DRAFT } from "@/types/setup";
import { getLessonLibrary, getSetupDraft, selectLessonInLibrary, setLessonLibrary, setSetupDraft, upsertLessonLibraryItem } from "@/lib/setup-storage";

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

export function useLessonLibraryState() {
  const [library, setLibraryState] = useState<LessonLibraryState>({ items: [], selectedLessonId: null });

  useEffect(() => setLibraryState(getLessonLibrary()), []);

  const addLesson = useCallback((item: LessonLibraryItem) => setLibraryState(upsertLessonLibraryItem(item)), []);
  const selectLesson = useCallback((lessonId: string | null) => setLibraryState(selectLessonInLibrary(lessonId)), []);
  const replaceLibrary = useCallback((state: LessonLibraryState) => { setLibraryState(state); setLessonLibrary(state); }, []);

  return useMemo(() => ({ library, addLesson, selectLesson, replaceLibrary }), [library, addLesson, selectLesson, replaceLibrary]);
}
