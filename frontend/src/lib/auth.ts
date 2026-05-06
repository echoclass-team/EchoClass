/**
 * 认证 token 存取（M3 #B1）。
 *
 * M3 最小化：access token 存 localStorage，无 refresh。
 * 写入/清除时派发自定义事件，供 React 组件订阅实现响应式刷新。
 */

const TOKEN_KEY = "echoclass_token";
const USERNAME_KEY = "echoclass_username";

export const AUTH_CHANGE_EVENT = "echoclass:auth-change";

function notifyAuthChange(): void {
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  notifyAuthChange();
}

export function getUsername(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(USERNAME_KEY);
}

export function setUsername(name: string): void {
  localStorage.setItem(USERNAME_KEY, name);
  notifyAuthChange();
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
  notifyAuthChange();
}

export function isLoggedIn(): boolean {
  return !!getToken();
}
