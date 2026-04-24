export interface SetupDraft {
  selectedStageId: string | null;
  selectedPersonaIds: string[];
  selectedLessonId: string | null;
}

export const DEFAULT_SETUP_DRAFT: SetupDraft = {
  selectedStageId: null,
  selectedPersonaIds: [],
  selectedLessonId: null,
};

export interface LessonLibraryItem {
  lessonId: string;
  title?: string | null;
  subtitle?: string | null;
  subject?: string | null;
  grade?: string | null;
  topic?: string | null;
  source: "remote" | "local" | "mock";
  status: "uploaded" | "ready" | "draft" | "archived";
  createdAt?: string | null;
  updatedAt?: string | null;
  objectives?: string[];
  key_points?: string[];
  difficult_points?: string[];
  [key: string]: unknown;
}

export interface LessonLibraryState {
  items: LessonLibraryItem[];
  selectedLessonId: string | null;
}
