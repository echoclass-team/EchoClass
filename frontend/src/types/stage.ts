export interface Stage {
  id: string;
  name: string;
  description?: string | null;
  grade_range?: string | null;
  age_range?: string | null;
  order?: number | null;
  [key: string]: unknown;
}
