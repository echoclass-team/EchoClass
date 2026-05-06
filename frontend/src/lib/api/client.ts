import { getToken } from "@/lib/auth";
import { getApiBase } from "@/lib/env";
import type { ApiResponse } from "./types";

/** API 错误：带 HTTP 状态码与后端 ApiResponse.code/message。 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: number;
  readonly requestId?: string;

  constructor(message: string, options: { status: number; code: number; requestId?: string }) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.requestId = options.requestId;
  }
}

/**
 * 统一的 API 请求入口。
 *
 * - 返回 ApiResponse<T>（已校验 code===0），调用方可直接访问 .data。
 * - 失败（HTTP 非 2xx 或 code !== 0）抛出 ApiError，message 来自后端 envelope。
 * - 后端已为所有错误统一包装为 ApiResponse 结构，见 backend/api/response.py。
 */
export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<ApiResponse<T>> {
  const base = getApiBase();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = `${base}${normalizedPath}`;
  const headers = new Headers(init.headers);
  const hasBody = init.body !== undefined && init.body !== null;
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;

  if (hasBody && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // M3 #B1: 自动注入 Bearer token
  const token = getToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(url, {
    ...init,
    cache: "no-store",
    headers,
  });

  // 尝试解析 JSON；body 可能不是 JSON（极端异常如网关 502）
  let body: Partial<ApiResponse<T>> | null = null;
  try {
    body = (await response.json()) as ApiResponse<T>;
  } catch {
    body = null;
  }

  if (!response.ok) {
    throw new ApiError(body?.message ?? `${response.status} ${response.statusText}`, {
      status: response.status,
      code: body?.code ?? response.status,
      requestId: body?.request_id,
    });
  }

  if (!body || typeof body.code !== "number") {
    throw new ApiError("响应体格式异常，缺少 ApiResponse 包络", {
      status: response.status,
      code: -1,
    });
  }

  if (body.code !== 0) {
    throw new ApiError(body.message ?? "业务错误", {
      status: response.status,
      code: body.code,
      requestId: body.request_id,
    });
  }

  return body as ApiResponse<T>;
}
