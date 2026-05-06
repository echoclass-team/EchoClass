/**
 * 认证 API 客户端（M3 #B1）。
 *
 * - POST /api/auth/register
 * - POST /api/auth/login
 */

import { apiFetch } from "./client";

interface RegisterData {
  user_id: string;
}

interface LoginData {
  access_token: string;
  token_type: string;
}

export async function apiRegister(username: string, password: string): Promise<RegisterData> {
  const res = await apiFetch<RegisterData>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  if (!res.data) throw new Error("注册失败：响应无数据");
  return res.data;
}

export async function apiLogin(username: string, password: string): Promise<LoginData> {
  const res = await apiFetch<LoginData>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  if (!res.data) throw new Error("登录失败：响应无数据");
  return res.data;
}
