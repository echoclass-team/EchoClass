"use client";

/**
 * QA WebSocket 调试页 — 手动验证 `lib/qa-ws.ts` + `useQASession` 全链路。
 *
 * 启动 mock server：
 *   cd backend
 *   uv run python scripts/mock_ws_server.py
 *
 * 然后访问 http://localhost:3000/qa/debug，默认连
 *   ws://localhost:8765/ws/qa-sessions/demo-session
 *
 * 本页非正式 UI，仅用于联调。正式 1v1 答疑界面见任务 #B5。
 */

import { useState } from "react";

import { useQASession } from "@/hooks/use-qa-session";

const DEFAULT_SESSION_ID = "demo-session";
const DEFAULT_WS_BASE = "ws://localhost:8765";

export default function QADebugPage() {
  const [sessionId, setSessionId] = useState(DEFAULT_SESSION_ID);
  const [wsBase, setWsBase] = useState(DEFAULT_WS_BASE);
  const [connected, setConnected] = useState(false);
  const [text, setText] = useState("");

  const {
    state,
    status,
    pendingCount,
    unresolvedCount,
    activeDialog,
    selectDialog,
    sendMessage,
    resolve,
    abandon,
    disconnect,
  } = useQASession({
    sessionId: connected ? sessionId : null,
    wsBase,
  });

  const isStreaming = activeDialog?.isStreaming ?? false;

  return (
    <main className="min-h-screen bg-slate-50 p-6 font-mono text-sm text-slate-900">
      <div className="mx-auto max-w-6xl space-y-4">
        <header className="rounded border border-slate-200 bg-white p-4">
          <h1 className="text-lg font-semibold">QA WS Debug</h1>
          <p className="mt-1 text-xs text-slate-500">
            手动验证 ws client + useQASession。配合 mock server 使用。
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-1">
              wsBase
              <input
                value={wsBase}
                onChange={(e) => setWsBase(e.target.value)}
                disabled={connected}
                className="rounded border border-slate-300 px-2 py-1"
              />
            </label>
            <label className="flex items-center gap-1">
              sessionId
              <input
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
                disabled={connected}
                className="rounded border border-slate-300 px-2 py-1"
              />
            </label>
            {!connected ? (
              <button
                onClick={() => setConnected(true)}
                className="rounded bg-blue-600 px-3 py-1 text-white"
              >
                Connect
              </button>
            ) : (
              <button
                onClick={() => {
                  disconnect();
                  setConnected(false);
                }}
                className="rounded bg-slate-700 px-3 py-1 text-white"
              >
                Disconnect
              </button>
            )}
            <span
              className={`ml-auto rounded px-2 py-0.5 text-xs ${
                status === "open"
                  ? "bg-emerald-100 text-emerald-700"
                  : status === "reconnecting"
                  ? "bg-amber-100 text-amber-700"
                  : status === "replaced"
                  ? "bg-rose-100 text-rose-700"
                  : "bg-slate-100 text-slate-700"
              }`}
            >
              status: {status}
            </span>
          </div>
        </header>

        <section className="grid grid-cols-[260px_1fr] gap-4">
          {/* 学生 / dialog 列表 */}
          <div className="space-y-2">
            <div className="rounded border border-slate-200 bg-white p-3">
              <div className="text-xs text-slate-500">教案</div>
              <div className="text-sm font-medium">
                {state.lesson?.topic ?? "—"}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                pending={pendingCount} / unresolved={unresolvedCount} / total=
                {state.dialogOrder.length}
              </div>
            </div>
            <div className="rounded border border-slate-200 bg-white">
              {state.dialogOrder.length === 0 ? (
                <div className="p-3 text-xs text-slate-400">未连接或无 dialog</div>
              ) : (
                state.dialogOrder.map((dialogId) => {
                  const d = state.dialogs[dialogId];
                  if (!d) return null;
                  const active = state.activeDialogId === d.id;
                  const icon =
                    d.status === "resolved"
                      ? "✓"
                      : d.status === "abandoned"
                      ? "✗"
                      : d.status === "active"
                      ? "·"
                      : "○";
                  return (
                    <button
                      key={d.id}
                      onClick={() => selectDialog(d.id)}
                      className={`block w-full border-b border-slate-100 p-2 text-left text-xs last:border-b-0 hover:bg-slate-50 ${
                        active ? "bg-blue-50" : ""
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-3">{icon}</span>
                        <span className="font-medium">
                          {d.question.speaker_name}
                        </span>
                        <span className="ml-auto text-slate-400">
                          {d.status}
                        </span>
                      </div>
                      <div className="mt-1 line-clamp-2 text-slate-600">
                        {d.question.content}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* 对话窗口 */}
          <div className="rounded border border-slate-200 bg-white p-3">
            {!activeDialog ? (
              <div className="text-xs text-slate-400">未选择 dialog</div>
            ) : (
              <>
                <div className="border-b border-slate-100 pb-2">
                  <div className="text-xs text-slate-500">
                    {activeDialog.question.speaker_name} · {activeDialog.status}
                    {activeDialog.lastSelfResolved && " · [懂了]"}
                  </div>
                  <div className="text-sm">{activeDialog.question.content}</div>
                </div>
                <div className="mt-2 max-h-[420px] space-y-2 overflow-y-auto">
                  {activeDialog.history.map((turn, i) => (
                    <div
                      key={i}
                      className={
                        turn.role === "teacher"
                          ? "rounded bg-slate-100 p-2"
                          : "rounded bg-blue-50 p-2"
                      }
                    >
                      <div className="text-xs text-slate-500">{turn.role}</div>
                      <div className="whitespace-pre-wrap">{turn.content}</div>
                      {turn.selfResolved && (
                        <div className="mt-1 text-xs text-emerald-600">
                          [懂了]
                        </div>
                      )}
                    </div>
                  ))}
                  {activeDialog.currentReply && (
                    <div className="rounded border border-blue-200 bg-blue-50 p-2">
                      <div className="text-xs text-blue-500">
                        student (streaming…)
                      </div>
                      <div className="whitespace-pre-wrap">
                        {activeDialog.currentReply}
                      </div>
                    </div>
                  )}
                </div>
                <form
                  className="mt-3 flex gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!text.trim()) return;
                    sendMessage(activeDialog.id, text);
                    setText("");
                  }}
                >
                  <input
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    disabled={
                      isStreaming ||
                      activeDialog.status === "resolved" ||
                      activeDialog.status === "abandoned"
                    }
                    placeholder={
                      isStreaming ? "学生正在回复…" : "输入师范生发言"
                    }
                    className="flex-1 rounded border border-slate-300 px-2 py-1"
                  />
                  <button
                    type="submit"
                    disabled={
                      isStreaming ||
                      activeDialog.status === "resolved" ||
                      activeDialog.status === "abandoned"
                    }
                    className="rounded bg-blue-600 px-3 py-1 text-white disabled:opacity-40"
                  >
                    发送
                  </button>
                </form>
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() =>
                      resolve(
                        activeDialog.id,
                        activeDialog.lastSelfResolved
                          ? "self_resolve"
                          : "teacher_marked",
                      )
                    }
                    disabled={
                      activeDialog.status === "resolved" ||
                      activeDialog.status === "abandoned"
                    }
                    className="rounded border border-emerald-500 px-3 py-1 text-emerald-700 disabled:opacity-40"
                  >
                    标记已解答
                  </button>
                  <button
                    onClick={() => abandon(activeDialog.id)}
                    disabled={
                      activeDialog.status === "resolved" ||
                      activeDialog.status === "abandoned"
                    }
                    className="rounded border border-slate-400 px-3 py-1 text-slate-700 disabled:opacity-40"
                  >
                    放弃
                  </button>
                </div>
              </>
            )}
          </div>
        </section>

        {state.lastError && (
          <pre className="rounded border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
            error: {JSON.stringify(state.lastError)}
          </pre>
        )}

        {state.summary && (
          <pre className="rounded border border-slate-200 bg-white p-3 text-xs">
            summary: {JSON.stringify(state.summary, null, 2)}
          </pre>
        )}
      </div>
    </main>
  );
}
