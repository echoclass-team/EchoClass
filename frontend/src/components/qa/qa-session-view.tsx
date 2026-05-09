"use client";

/**
 * #B5 主 UI 容器：左侧学生列表 + 右侧对话窗口 + 顶部教案信息条。
 *
 * 数据源：`useQASession` 返回的 state（dialogs / dialogOrder / activeDialogId / students / lesson）。
 * 命令：selectDialog / sendMessage / resolve / abandon / disconnect。
 *
 * 退出流程：
 * - 全部 dialog 都进入终态（resolved/abandoned）时，"结束陪练"按钮高亮
 * - 点"结束陪练" → 调 POST /api/qa-sessions/{id}/end → 跳 /qa/{id}/summary
 * - 不在这里直接调 hook.disconnect()；让 summary 页加载完再 disconnect WS
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { endQASession } from "@/lib/api/qa";
import { saveQASummary } from "@/lib/qa-summary-storage";
import type { DialogState, QASessionState } from "@/hooks/use-qa-session";
import type { QAWsStatus } from "@/lib/qa-ws";
import type { WsStudentInfo } from "@/lib/qa-ws.types";

interface Props {
  state: QASessionState;
  status: QAWsStatus;
  pendingCount: number;
  unresolvedCount: number;
  activeDialog: DialogState | null;
  selectDialog: (dialogId: string) => void;
  sendMessage: (dialogId: string, text: string) => void;
  resolve: (dialogId: string, source?: "teacher_marked" | "self_resolve") => void;
  abandon: (dialogId: string) => void;
  disconnect: () => void;
}

export function QASessionView(props: Props) {
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
  } = props;
  const router = useRouter();
  const [endingError, setEndingError] = useState("");
  const [ending, setEnding] = useState(false);

  const allDone = state.dialogOrder.length > 0 && unresolvedCount === 0;

  const handleEnd = async () => {
    if (!state.sessionId) return;
    setEnding(true);
    setEndingError("");
    try {
      const data = await endQASession(state.sessionId);
      // REST 返回的 summary 是权威；如果 WS 已经推过 summary 帧也并入做兜底字段
      const merged = {
        ...(state.summary ?? {}),
        ...data.summary,
      } as typeof data.summary;
      saveQASummary(state.sessionId, merged);
      // 拿到 summary 后断 WS（避免服务器误判 replaced），再跳复盘页
      disconnect();
      router.push(`/review/${encodeURIComponent(state.sessionId)}`);
    } catch (err) {
      setEnding(false);
      setEndingError(err instanceof Error ? err.message : "结束陪练失败");
    }
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col bg-slate-50">
      <LessonInfoBar
        state={state}
        status={status}
        pendingCount={pendingCount}
        unresolvedCount={unresolvedCount}
        allDone={allDone}
        ending={ending}
        endingError={endingError}
        onEnd={handleEnd}
      />

      <div className="flex flex-1 min-h-0">
        <StudentSidebar
          state={state}
          activeDialogId={state.activeDialogId}
          onSelectDialog={selectDialog}
        />
        <DialogPane
          activeDialog={activeDialog}
          status={status}
          onSendMessage={(text) => activeDialog && sendMessage(activeDialog.id, text)}
          onResolve={(source) => activeDialog && resolve(activeDialog.id, source)}
          onAbandon={() => activeDialog && abandon(activeDialog.id)}
        />
      </div>
    </div>
  );
}

// ============================================================ Top bar

function LessonInfoBar({
  state,
  status,
  pendingCount,
  unresolvedCount,
  allDone,
  ending,
  endingError,
  onEnd,
}: {
  state: QASessionState;
  status: QAWsStatus;
  pendingCount: number;
  unresolvedCount: number;
  allDone: boolean;
  ending: boolean;
  endingError: string;
  onEnd: () => void;
}) {
  const lesson = state.lesson;
  const totalDialogs = state.dialogOrder.length;
  const resolvedCount = totalDialogs - unresolvedCount;

  return (
    <div className="border-b border-slate-200 bg-white">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 px-6 py-3 text-sm sm:px-10">
        <span className="font-semibold text-slate-900">
          {lesson?.topic || "—"}
        </span>
        <span className="text-slate-500">
          {lesson ? `${lesson.subject} · ${lesson.grade}` : "（教案加载中）"}
        </span>
        <span className="text-slate-400">·</span>
        <span className="text-slate-600">
          已解答 {resolvedCount} / {totalDialogs}
        </span>
        {pendingCount > 0 && (
          <span className="text-rose-600">未解答 {pendingCount}</span>
        )}

        <div className="ml-auto flex items-center gap-3">
          <ConnectionBadge status={status} />
          <button
            type="button"
            disabled={ending}
            onClick={onEnd}
            className={`inline-flex items-center justify-center rounded-full px-5 py-2 text-sm font-semibold transition ${
              allDone
                ? "bg-emerald-600 text-white shadow-md shadow-emerald-600/20 hover:-translate-y-0.5 hover:bg-emerald-700"
                : "border border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50"
            } disabled:cursor-not-allowed disabled:opacity-60`}
            title={allDone ? "全部对话已结束，点击查看总结" : "提前结束陪练（未完成的将记为 pending）"}
          >
            {ending ? "结束中…" : allDone ? "查看总结 →" : "结束陪练"}
          </button>
        </div>
      </div>
      {endingError && (
        <p className="mx-6 mb-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-xs text-rose-700 sm:mx-10">
          ⚠ {endingError}
        </p>
      )}
    </div>
  );
}

function ConnectionBadge({ status }: { status: QAWsStatus }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${meta.className}`}
    >
      <span className={`size-1.5 rounded-full ${meta.dot}`} aria-hidden />
      {meta.label}
    </span>
  );
}

const STATUS_META: Record<QAWsStatus, { label: string; className: string; dot: string }> = {
  idle: { label: "未连接", className: "bg-slate-100 text-slate-600", dot: "bg-slate-400" },
  connecting: {
    label: "连接中",
    className: "bg-amber-50 text-amber-700",
    dot: "bg-amber-500 animate-pulse",
  },
  open: {
    label: "已连接",
    className: "bg-emerald-50 text-emerald-700",
    dot: "bg-emerald-500",
  },
  reconnecting: {
    label: "重连中",
    className: "bg-amber-50 text-amber-700",
    dot: "bg-amber-500 animate-pulse",
  },
  closed: { label: "已断开", className: "bg-slate-100 text-slate-600", dot: "bg-slate-400" },
  replaced: { label: "已被新连接挤掉", className: "bg-rose-50 text-rose-700", dot: "bg-rose-500" },
};

// ============================================================ Sidebar

// ---- dismissed badge persistence (localStorage) ----

const DISMISSED_KEY_PREFIX = "echoclass.qa.dismissed.";

function getDismissedSet(sessionId: string | null): Set<string> {
  if (!sessionId || typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem(DISMISSED_KEY_PREFIX + sessionId);
    return raw ? new Set(JSON.parse(raw) as string[]) : new Set();
  } catch {
    return new Set();
  }
}

function persistDismissed(sessionId: string | null, set: Set<string>): void {
  if (!sessionId || typeof window === "undefined") return;
  try {
    localStorage.setItem(DISMISSED_KEY_PREFIX + sessionId, JSON.stringify(Array.from(set)));
  } catch { /* ignore */ }
}

function StudentSidebar({
  state,
  activeDialogId,
  onSelectDialog,
}: {
  state: QASessionState;
  activeDialogId: string | null;
  onSelectDialog: (id: string) => void;
}) {
  /** 按学生分组 dialog id，保持 dialogOrder 中的顺序。 */
  const groups = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const did of state.dialogOrder) {
      const dialog = state.dialogs[did];
      if (!dialog) continue;
      const sid = dialog.question.speaker_id;
      const arr = map.get(sid) ?? [];
      arr.push(did);
      map.set(sid, arr);
    }
    return map;
  }, [state.dialogOrder, state.dialogs]);

  const [dismissed, setDismissed] = useState<Set<string>>(() => getDismissedSet(state.sessionId));

  const handleSelect = useCallback(
    (studentId: string, dialogIds: string[]) => {
      if (dialogIds.length > 0) onSelectDialog(dialogIds[0]);
      setDismissed((prev) => {
        if (prev.has(studentId)) return prev;
        const next = new Set(prev);
        next.add(studentId);
        persistDismissed(state.sessionId, next);
        return next;
      });
    },
    [onSelectDialog, state.sessionId],
  );

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-5 py-3">
        <p className="text-xs font-semibold tracking-[0.2em] text-slate-500 uppercase">
          学生 · {state.students.length}
        </p>
      </div>
      <ul className="flex-1 space-y-1 overflow-y-auto px-2 py-3">
        {state.students.map((student) => {
          const dialogIds = groups.get(student.id) ?? [];
          return (
            <StudentSection
              key={student.id}
              student={student}
              dialogIds={dialogIds}
              dialogs={state.dialogs}
              activeDialogId={activeDialogId}
              dismissed={dismissed.has(student.id)}
              onSelectDialog={() => handleSelect(student.id, dialogIds)}
            />
          );
        })}
        {state.students.length === 0 && (
          <li className="px-3 py-6 text-center text-sm text-slate-400">
            等待 session_init…
          </li>
        )}
      </ul>
    </aside>
  );
}

function StudentSection({
  student,
  dialogIds,
  dialogs,
  activeDialogId,
  dismissed,
  onSelectDialog,
}: {
  student: WsStudentInfo;
  dialogIds: string[];
  dialogs: Record<string, DialogState>;
  activeDialogId: string | null;
  dismissed: boolean;
  onSelectDialog: () => void;
}) {
  const unresolved = dialogIds.filter((id) => {
    const d = dialogs[id];
    return d && (d.status === "pending" || d.status === "active");
  }).length;
  const allDone = dialogIds.length > 0 && unresolved === 0;
  const initial = student.name.charAt(0);
  const isActive = dialogIds.some((id) => id === activeDialogId);
  const firstDialog = dialogIds.length > 0 ? dialogs[dialogIds[0]] : null;
  const preview = firstDialog?.question.content ?? "";

  const showBadge = unresolved > 0 && !dismissed;

  return (
    <li>
      <button
        type="button"
        onClick={onSelectDialog}
        className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
          isActive
            ? "bg-slate-900 text-white"
            : "text-slate-900 hover:bg-slate-100"
        }`}
      >
        <div
          className={`flex size-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${
            isActive
              ? "bg-white/20 text-white"
              : allDone
                ? "bg-emerald-100 text-emerald-700"
                : "bg-sky-100 text-sky-700"
          }`}
        >
          {initial}
        </div>
        <div className="min-w-0 flex-1">
          <p className={`truncate text-sm font-semibold ${isActive ? "text-white" : "text-slate-900"}`}>
            {student.name}
          </p>
          {preview && (
            <p className={`mt-0.5 truncate text-xs ${isActive ? "text-slate-300" : "text-slate-500"}`}>
              {preview}
            </p>
          )}
        </div>
        {showBadge ? (
          <span className={`inline-flex min-w-[1.5rem] items-center justify-center rounded-full px-1.5 text-xs font-semibold ${
            isActive ? "bg-rose-400 text-white" : "bg-rose-500 text-white"
          }`}>
            {unresolved}
          </span>
        ) : allDone ? (
          <span className={isActive ? "text-emerald-300" : "text-emerald-600"} aria-label="全部已解答">
            ✓
          </span>
        ) : null}
      </button>
    </li>
  );
}

// ============================================================ Dialog pane

function DialogPane({
  activeDialog,
  status,
  onSendMessage,
  onResolve,
  onAbandon,
}: {
  activeDialog: DialogState | null;
  status: QAWsStatus;
  onSendMessage: (text: string) => void;
  onResolve: (source?: "teacher_marked" | "self_resolve") => void;
  onAbandon: () => void;
}) {
  if (!activeDialog) {
    return (
      <main className="flex flex-1 items-center justify-center bg-slate-50 p-10 text-center text-slate-500">
        <div>
          <p className="text-base font-medium text-slate-700">点左侧某条问题开始 1v1 答疑。</p>
          <p className="mt-2 text-sm">每位学生可能会问多个问题，逐个解答；可随时切换。</p>
        </div>
      </main>
    );
  }

  const ended =
    activeDialog.status === "resolved" || activeDialog.status === "abandoned";

  return (
    <main className="flex flex-1 flex-col bg-slate-50">
      <DialogHeader dialog={activeDialog} onResolve={onResolve} onAbandon={onAbandon} />
      <DialogHistory dialog={activeDialog} />
      {activeDialog.lastSelfResolved && !ended && (
        <div className="mx-6 -mb-1 mt-3 flex items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800 sm:mx-auto sm:max-w-3xl sm:w-[calc(100%-3rem)]">
          <span>🎉 {activeDialog.question.speaker_name} 表示懂了，可以标记为已解答。</span>
          <button
            type="button"
            onClick={() => onResolve("self_resolve")}
            className="inline-flex items-center justify-center rounded-full bg-emerald-600 px-3 py-1 text-xs font-semibold text-white transition hover:bg-emerald-700"
          >
            标记已解答
          </button>
        </div>
      )}
      <DialogInput
        dialog={activeDialog}
        wsStatus={status}
        onSubmit={onSendMessage}
      />
    </main>
  );
}

function DialogHeader({
  dialog,
  onResolve,
  onAbandon,
}: {
  dialog: DialogState;
  onResolve: (source?: "teacher_marked" | "self_resolve") => void;
  onAbandon: () => void;
}) {
  const ended = dialog.status === "resolved" || dialog.status === "abandoned";
  return (
    <header className="border-b border-slate-200 bg-white px-6 py-4">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold tracking-[0.2em] text-slate-500 uppercase">
            {dialog.question.speaker_name} · {dialog.question.category}
          </p>
          <p className="mt-1 text-base font-semibold text-slate-900">
            {dialog.question.content}
          </p>
          {dialog.question.linked_key_point && (
            <p className="mt-1 text-xs text-sky-700">
              关联重点：{dialog.question.linked_key_point}
            </p>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          {!ended && (
            <>
              <button
                type="button"
                onClick={() => onResolve("teacher_marked")}
                className="inline-flex items-center justify-center rounded-full border border-emerald-300 bg-emerald-50 px-4 py-1.5 text-xs font-semibold text-emerald-700 transition hover:bg-emerald-100"
              >
                标记已解答
              </button>
              <button
                type="button"
                onClick={onAbandon}
                className="inline-flex items-center justify-center rounded-full border border-slate-300 bg-white px-4 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50"
              >
                放弃
              </button>
            </>
          )}
          {dialog.status === "resolved" && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-3 py-1.5 text-xs font-semibold text-emerald-700">
              ✓ 已解答（{dialog.resolutionSource ?? "—"}）
            </span>
          )}
          {dialog.status === "abandoned" && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600">
              ✗ 已放弃
            </span>
          )}
        </div>
      </div>
    </header>
  );
}

function DialogHistory({ dialog }: { dialog: DialogState }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  // 自动滚到底；history / currentReply 任一变化都触发
  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [dialog.history.length, dialog.currentReply, dialog.id]);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-6 py-6"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {/* 学生最初的问题作为第一条消息 */}
        <Bubble
          role="student"
          name={dialog.question.speaker_name}
          content={dialog.question.content}
        />

        {dialog.history.map((turn, idx) => (
          <Bubble
            key={idx}
            role={turn.role}
            name={turn.role === "teacher" ? "你" : dialog.question.speaker_name}
            content={turn.content}
            selfResolved={turn.selfResolved}
            isNewQuestion={turn.isNewQuestion}
          />
        ))}

        {/* 8轮耗尽提示：对话终态且最后一条是学生消息（turn_limit 场景） */}
        {(dialog.status === "resolved" || dialog.status === "abandoned") &&
          dialog.resolutionSource === "turn_limit" && (
            <div className="mx-auto flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-700">
              ⏳ 对话轮数已用尽，学生将进入下一问题的环节。
            </div>
          )}

        {/* 流式中的学生回复（不在 history 中） */}
        {dialog.isStreaming && dialog.currentReply && (
          <Bubble
            role="student"
            name={dialog.question.speaker_name}
            content={dialog.currentReply}
            streaming
          />
        )}
        {dialog.isStreaming && !dialog.currentReply && (
          <Bubble role="student" name={dialog.question.speaker_name} content="…" streaming />
        )}
      </div>
    </div>
  );
}

function Bubble({
  role,
  name,
  content,
  selfResolved,
  streaming,
  isNewQuestion,
}: {
  role: "teacher" | "student";
  name: string;
  content: string;
  selfResolved?: boolean;
  streaming?: boolean;
  isNewQuestion?: boolean;
}) {
  const isTeacher = role === "teacher";
  return (
    <div className={`flex gap-3 ${isTeacher ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex size-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${
          isTeacher ? "bg-slate-900 text-white" : "bg-sky-100 text-sky-700"
        }`}
      >
        {name.charAt(0)}
      </div>
      <div className={`flex max-w-[80%] flex-col ${isTeacher ? "items-end" : "items-start"}`}>
        <p className="mb-1 text-xs font-medium text-slate-500">
          {name}
          {isNewQuestion && (
            <span className="ml-1.5 inline-flex items-center rounded-full bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700">
              新问题
            </span>
          )}
        </p>
        <div
          className={`whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm ${
            isTeacher
              ? "bg-slate-900 text-white"
              : isNewQuestion
                ? "border border-violet-200 bg-violet-50 text-slate-800"
                : "border border-slate-200 bg-white text-slate-800"
          } ${streaming ? "animate-pulse-soft" : ""}`}
        >
          {content}
          {streaming && <span className="ml-0.5 inline-block animate-pulse">▍</span>}
        </div>
        {selfResolved && (
          <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
            🎉 [懂了]
          </span>
        )}
      </div>
    </div>
  );
}

function DialogInput({
  dialog,
  wsStatus,
  onSubmit,
}: {
  dialog: DialogState;
  wsStatus: QAWsStatus;
  onSubmit: (text: string) => void;
}) {
  const [value, setValue] = useState("");
  const ended = dialog.status === "resolved" || dialog.status === "abandoned";
  const wsReady = wsStatus === "open";
  const disabled = dialog.isStreaming || ended || !wsReady;

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setValue("");
  };

  return (
    <footer className="border-t border-slate-200 bg-white px-6 py-4">
      <div className="mx-auto max-w-3xl">
        <div
          className={`flex items-end gap-2 rounded-2xl border px-3 py-2.5 transition ${
            disabled
              ? "border-slate-200 bg-slate-50"
              : "border-slate-300 bg-white focus-within:border-sky-400 focus-within:ring-2 focus-within:ring-sky-100"
          }`}
        >
          <textarea
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (!disabled) handleSend();
              }
            }}
            rows={1}
            placeholder={
              ended
                ? "本对话已结束。"
                : !wsReady
                  ? "WS 未就绪…"
                  : dialog.isStreaming
                    ? "学生正在回复…"
                    : "回车发送，Shift+回车换行"
            }
            disabled={disabled}
            className="flex-1 resize-none bg-transparent text-sm leading-relaxed text-slate-900 placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed"
            style={{ minHeight: "2.25rem", maxHeight: "8rem" }}
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={disabled || value.trim().length === 0}
            className="inline-flex shrink-0 items-center justify-center rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            发送
          </button>
        </div>
      </div>
    </footer>
  );
}
