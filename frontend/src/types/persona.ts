export interface Persona {
  id: string;
  name: string;
  title?: string | null;
  description?: string | null;
  gender?: string | null;
  grade?: string | null;
  age?: number | null;
  stage_id?: string | null;
  subject_level?: string | null;
  summary?: string | null;
  [key: string]: unknown;
}
