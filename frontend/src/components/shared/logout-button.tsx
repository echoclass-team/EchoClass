"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AUTH_CHANGE_EVENT, clearAuth, getUsername } from "@/lib/auth";

export function LogoutButton() {
  const router = useRouter();
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    const sync = () => setUsername(getUsername());
    sync();
    window.addEventListener(AUTH_CHANGE_EVENT, sync);
    return () => window.removeEventListener(AUTH_CHANGE_EVENT, sync);
  }, []);

  if (!username) return null;

  return (
    <span className="flex items-center gap-2 text-sm text-slate-500">
      <span className="hidden sm:inline">{username}</span>
      <button
        type="button"
        onClick={() => {
          clearAuth();
          router.push("/login");
        }}
        className="text-slate-400 transition hover:text-slate-600"
      >
        退出
      </button>
    </span>
  );
}
