export interface LessonUploadData {
  lesson_id: string;
  subject: string;
  grade: string;
  topic: string;
  objectives: string[];
  key_points: string[];
  difficult_points: string[];
}

export interface LessonRecord {
  lesson_id: string;
  filename: string;
  meta: {
    subject: string;
    grade: string;
    topic: string;
    objectives: string[];
    key_points: string[];
    difficult_points: string[];
  };
  text_length: number;
  chunk_count: number;
}

export interface LessonLibraryItem {
  lessonId: string;
  title: string;
  subject: string;
  grade: string;
  topic: string;
  source: "seed" | "uploaded" | "local";
  status: "ready" | "draft" | "archived";
  createdAt?: string | null;
  updatedAt?: string | null;
}
