"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { apiLogin } from "@/lib/api/auth";
import { setToken, setUsername } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsernameInput] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await apiLogin(username, password);
      setToken(data.access_token);
      setUsername(username);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
          <h1 className="text-center text-2xl font-semibold tracking-tight text-slate-950">
            登录 EchoClass
          </h1>
          <p className="mt-2 text-center text-sm text-slate-500">
            AI 答疑陪练系统
          </p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-4">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-slate-700">
                用户名
              </label>
              <input
                id="username"
                type="text"
                required
                autoComplete="username"
                value={username}
                onChange={(e) => setUsernameInput(e.target.value)}
                className="mt-1 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                placeholder="请输入用户名"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                密码
              </label>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
                placeholder="请输入密码"
              />
            </div>

            {error && (
              <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-600">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50"
            >
              {loading ? "登录中…" : "登录"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-500">
            没有账号？{" "}
            <Link href="/register" className="font-medium text-sky-600 hover:text-sky-500">
              注册
            </Link>
          </p>
        </div>
      </div>
    </main>
  );
}
