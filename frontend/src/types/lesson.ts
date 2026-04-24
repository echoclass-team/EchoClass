/**
 * 教案结构化抽取结果，对应后端 `LessonUploadData`（POST /api/lessons/upload 的 data）。
 * 字段定义见 backend/schemas/lesson.py::LessonUploadData。
 */
export interface LessonMeta {
  subject: string;
  grade: string;
  topic: string;
  objectives: string[];
  key_points: string[];
  difficult_points: string[];
}

/**
 * POST /api/lessons/upload 的 data 载荷。
 */
export interface LessonUploadData extends LessonMeta {
  lesson_id: string;
}

/**
 * GET /api/lessons/{lesson_id} 的 data 载荷，对应后端 `LessonRecord`。
 */
export interface LessonRecord {
  lesson_id: string;
  filename: string;
  meta: LessonMeta;
  text_length: number;
  chunk_count: number;
}

// 注意：前端本地教案库条目（LessonLibraryItem）是纯前端概念，
// 定义在 @/types/setup.ts，与后端 schema 无直接对应关系。
