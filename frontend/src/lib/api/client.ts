import { getApiBase } from "@/lib/env";
import type { ApiResponse } from "./types";

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<ApiResponse<T>> {
  const base = getApiBase();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = `${base}${normalizedPath}`;
  const headers = new Headers(init.headers);
  const hasBody = init.body !== undefined && init.body !== null;
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;

  if (hasBody && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...init,
    cache: "no-store",
    headers,
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<ApiResponse<T>>;
}
