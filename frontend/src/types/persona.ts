/**
 * 学生人设概要，对应后端 `PersonaSummary`（GET /api/personas）。
 * 完整字段见 `PersonaDetail` / 后端 `backend/schemas/student.py::Persona`。
 */
export interface Persona {
  id: string;
  name: string;
  gender: string;
  grade: string;
  age: number;
  stage_id: string;
  subject_level: string;
  summary: string;
}

/**
 * 学生人设完整字段，对应后端 `Persona`（GET /api/personas/{name_or_id}）。
 * 完整字段定义见 backend/schemas/student.py::Persona。
 */
export interface PersonaDetail extends Persona {
  age: number;
  cognitive_stage: string;
  personality: string;
  speech_style: string;
  catchphrases: string[];
  misconception_tendencies: string[];
  attention_span: string;
  interaction_frequency: string;
  behavior_traits: string | string[];
  emotional_tendency: string;
  learning_motivation: string;
  family_background: string;
  avatar_seed: string;
  knowledge_level: string;
}
