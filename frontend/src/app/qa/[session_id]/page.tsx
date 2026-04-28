"use client";

/**
 * #B5: 1v1 答疑陪练主页面。
 *
 * - 由 setup flow 创建出 session_id 后由 router 跳转到这里
 * - 用 `useQASession` 维护 WS + state；UI 渲染交给 `QASessionView`
 * - 路由参数 session_id 直接作为 hook 输入；hook 自己负责连/断
 *
 * 联调：
 * - 真后端：直接用默认 wsBase（NEXT_PUBLIC_API_BASE → ws/wss）
 * - mock server：用 /qa/debug 页（已有，单独路由）
 */

import { QASessionView } from "@/components/qa/qa-session-view";
import { useQASession } from "@/hooks/use-qa-session";

export default function QASessionPage({
  params,
}: {
  params: { session_id: string };
}) {
  const ctx = useQASession({ sessionId: params.session_id });

  return <QASessionView {...ctx} />;
}
