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
 *
 * v1.3 (2026-05-07)：移除 personality / catchphrases / family_background。
 *   人设质感由 speech_style + behavior_traits + theory_anchors + summary 联合承载。
 * v1.1 (2026-04-25)：移除 4 个死字段（cognitive_stage / interaction_frequency /
 *   emotional_tendency / learning_motivation），认知阶段由 stage.piaget_stage 统一约束。
 */
export interface PersonaDetail extends Persona {
  age: number;
  speech_style: string;
  misconception_tendencies: string[];
  attention_span: string;
  behavior_traits: string | string[];
  avatar_seed: string;
  knowledge_level: string;
}
