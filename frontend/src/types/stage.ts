/**
 * 学段概要，对应后端 `StageSummary`（GET /api/stages）。
 * 完整字段见 `StageDetail` / 后端 `backend/schemas/stage.py::StageProfile`。
 */
export interface Stage {
  id: string;
  name: string;
  grade_range: string;
  age_range: string;
}

/**
 * 学段详情，对应后端 `StageProfile`（GET /api/stages/{id}）。
 * 完整字段定义见 backend/schemas/stage.py。
 */
export interface StageDetail extends Stage {
  piaget_stage: string;
  cognitive_features: string[];
  thinking_style: string;
  language_style: string;
  typical_expressions: string[];
  attention_features: string;
  memory_features: string;
  erikson_stage: string;
  emotional_features: string[];
  self_awareness: string;
  peer_relationship: string;
  motivation_patterns: string[];
  classroom_behaviors: string[];
  common_misconception_patterns: string[];
  teaching_implications: string[];
  sources: string[];
}
