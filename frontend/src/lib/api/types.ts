export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T | null;
  request_id: string;
}
