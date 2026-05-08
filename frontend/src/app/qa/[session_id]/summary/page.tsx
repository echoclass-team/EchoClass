"use client";

/**
 * Summary 页已迁移至 /review/[session_id]。
 * 本页仅做 redirect 兼容旧链接。
 */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { clearQASummary } from "@/lib/qa-summary-storage";

export default function QASummaryPage({
  params,
}: {
  params: { session_id: string };
}) {
  const router = useRouter();
  const sessionId = params.session_id;

  useEffect(() => {
    clearQASummary(sessionId);
    router.replace(`/review/${encodeURIComponent(sessionId)}`);
  }, [router, sessionId]);

  return (
    <main className="px-6 py-12 text-center text-sm text-slate-500">
      正在跳转到复盘页…
    </main>
  );
}
