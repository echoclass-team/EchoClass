"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { isLoggedIn } from "@/lib/auth";

/** 不需要登录即可访问的路径。 */
const PUBLIC_PATHS = ["/login", "/register"];

/**
 * 全局认证守卫（M3 #B1）。
 *
 * 在 root layout 中包裹 children，对非公开路径检查登录态，
 * 未登录自动跳转 /login。
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));

  useEffect(() => {
    if (isPublic) {
      setReady(true);
      return;
    }
    if (!isLoggedIn()) {
      router.replace("/login");
    } else {
      setReady(true);
    }
  }, [pathname, isPublic, router]);

  if (!ready && !isPublic) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-slate-400">加载中…</p>
      </div>
    );
  }

  return <>{children}</>;
}
