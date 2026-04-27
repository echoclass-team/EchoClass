/**
 * useQASession — 1v1 答疑陪练 React Hook。
 *
 * 在 React 端封装 `lib/qa-ws.ts` 客户端：
 * - 维护 sessionId / lesson / students / dialogs 全量状态
 * - 暴露 selectDialog / sendMessage / resolve / abandon 命令
 * - 自动应用增量事件（reply_chunk → currentReply；reply_end → push history）
 *
 * 设计取舍：
 * - 当前实现使用 React 原生 useReducer，**无 Zustand 依赖**。
 *   后续若多组件要共享同一 session 状态，可把 reducer 搬进 Zustand store，
 *   hook 接口保持兼容。
 * - 一个 hook 实例 = 一条 WebSocket 连接。请只在页面顶层调用一次，
 *   再用 props / context 把 state 传下去。
 *
 * 用法：
 * ```tsx
 * const { state, status, selectDialog, sendMessage } = useQASession({
 *   sessionId: "demo-session",
 *   wsBase: "ws://localhost:8765",
 * });
 * ```
 */

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";

import { createQAWs, type QAWsClient, type QAWsStatus } from "@/lib/qa-ws";
import type {
  LessonMeta,
  ResolutionSource,
  StudentQuestion,
  WsError,
  WsStudentInfo,
} from "@/lib/qa-ws.types";

// ============================================================ State 模型

/** 单条对话回合（已落地的 teacher / student 消息）。 */
export interface DialogTurn {
  role: "teacher" | "student";
  content: string;
  /** 仅 student 回合：LLM 是否在末尾标了 [懂了]。 */
  selfResolved?: boolean;
  /** 浏览器本地时间戳（ms）。 */
  timestamp: number;
}

/** 单个 dialog 的运行时状态。 */
export interface DialogState {
  id: string;
  question: StudentQuestion;
  status: "pending" | "active" | "resolved" | "abandoned";
  /** 已完成回合（teacher 一条 + student 一条交替）。 */
  history: DialogTurn[];
  /** 当前正在流式输出的学生回复缓冲；reply_end 后清空并 push 入 history。 */
  currentReply: string;
  /** 是否正在收 reply_chunk（用于禁用发送按钮）。 */
  isStreaming: boolean;
  /** 上一条 student 回复是否触发了 [懂了]。 */
  lastSelfResolved: boolean;
  /** 仅在 resolved/abandoned 时填。 */
  resolutionSource?: ResolutionSource;
}

/** Hook 维护的全部业务状态。 */
export interface QASessionState {
  sessionId: string | null;
  lesson: LessonMeta | null;
  students: WsStudentInfo[];
  /** key = dialog_id；用对象代替 Map，便于浅比较与序列化。 */
  dialogs: Record<string, DialogState>;
  /** 与 dialogs 同步的稳定顺序（== session_init.questions 顺序）。 */
  dialogOrder: string[];
  activeDialogId: string | null;
  /** 服务端推过来的最新 summary（关连接前一帧），用于 summary 页。 */
  summary: Record<string, unknown> | null;
  /** 最近一次错误帧。 */
  lastError: WsError | null;
}

const initialState: QASessionState = {
  sessionId: null,
  lesson: null,
  students: [],
  dialogs: {},
  dialogOrder: [],
  activeDialogId: null,
  summary: null,
  lastError: null,
};

// ============================================================ Reducer

type Action =
  | { type: "RESET" }
  | {
      type: "SESSION_INIT";
      sessionId: string;
      lesson: LessonMeta;
      students: WsStudentInfo[];
      questions: StudentQuestion[];
    }
  | { type: "DIALOG_ACTIVE"; dialogId: string }
  | { type: "TEACHER_MESSAGE_OPTIMISTIC"; dialogId: string; text: string }
  | { type: "REPLY_CHUNK"; dialogId: string; delta: string }
  | {
      type: "REPLY_END";
      dialogId: string;
      fullContent: string;
      selfResolved: boolean;
    }
  | {
      type: "DIALOG_RESOLVED";
      dialogId: string;
      source: "teacher_marked" | "self_resolve";
    }
  | { type: "DIALOG_ABANDONED"; dialogId: string }
  | { type: "SUMMARY"; data: Record<string, unknown> }
  | { type: "ERROR"; error: WsError };

function reducer(state: QASessionState, action: Action): QASessionState {
  switch (action.type) {
    case "RESET":
      return initialState;

    case "SESSION_INIT": {
      const dialogs: Record<string, DialogState> = {};
      const order: string[] = [];
      for (const q of action.questions) {
        dialogs[q.id] = {
          id: q.id,
          question: q,
          status: "pending",
          history: [],
          currentReply: "",
          isStreaming: false,
          lastSelfResolved: false,
        };
        order.push(q.id);
      }
      return {
        ...state,
        sessionId: action.sessionId,
        lesson: action.lesson,
        students: action.students,
        dialogs,
        dialogOrder: order,
        activeDialogId: null,
        summary: null,
        lastError: null,
      };
    }

    case "DIALOG_ACTIVE": {
      const dialog = state.dialogs[action.dialogId];
      if (!dialog) return { ...state, activeDialogId: action.dialogId };
      const next: DialogState =
        dialog.status === "pending" ? { ...dialog, status: "active" } : dialog;
      return {
        ...state,
        activeDialogId: action.dialogId,
        dialogs:
          next === dialog
            ? state.dialogs
            : { ...state.dialogs, [action.dialogId]: next },
      };
    }

    case "TEACHER_MESSAGE_OPTIMISTIC": {
      const dialog = state.dialogs[action.dialogId];
      if (!dialog) return state;
      const next: DialogState = {
        ...dialog,
        status: dialog.status === "pending" ? "active" : dialog.status,
        history: [
          ...dialog.history,
          {
            role: "teacher",
            content: action.text,
            timestamp: Date.now(),
          },
        ],
        currentReply: "",
        isStreaming: true,
        lastSelfResolved: false,
      };
      return {
        ...state,
        dialogs: { ...state.dialogs, [action.dialogId]: next },
      };
    }

    case "REPLY_CHUNK": {
      const dialog = state.dialogs[action.dialogId];
      if (!dialog) return state;
      const next: DialogState = {
        ...dialog,
        currentReply: dialog.currentReply + action.delta,
        isStreaming: true,
      };
      return {
        ...state,
        dialogs: { ...state.dialogs, [action.dialogId]: next },
      };
    }

    case "REPLY_END": {
      const dialog = state.dialogs[action.dialogId];
      if (!dialog) return state;
      // 用 full_content 校正，落地 history
      const next: DialogState = {
        ...dialog,
        history: [
          ...dialog.history,
          {
            role: "student",
            content: action.fullContent,
            selfResolved: action.selfResolved,
            timestamp: Date.now(),
          },
        ],
        currentReply: "",
        isStreaming: false,
        lastSelfResolved: action.selfResolved,
      };
      return {
        ...state,
        dialogs: { ...state.dialogs, [action.dialogId]: next },
      };
    }

    case "DIALOG_RESOLVED": {
      const dialog = state.dialogs[action.dialogId];
      if (!dialog) return state;
      const next: DialogState = {
        ...dialog,
        status: "resolved",
        resolutionSource: action.source,
        isStreaming: false,
      };
      return {
        ...state,
        dialogs: { ...state.dialogs, [action.dialogId]: next },
        // 解决后保留 activeDialogId 不变；UI 自行决定切到下一个
      };
    }

    case "DIALOG_ABANDONED": {
      const dialog = state.dialogs[action.dialogId];
      if (!dialog) return state;
      const next: DialogState = {
        ...dialog,
        status: "abandoned",
        resolutionSource: "abandoned",
        isStreaming: false,
      };
      return {
        ...state,
        dialogs: { ...state.dialogs, [action.dialogId]: next },
      };
    }

    case "SUMMARY":
      return { ...state, summary: action.data };

    case "ERROR":
      return { ...state, lastError: action.error };

    default:
      return state;
  }
}

// ============================================================ Hook 接口

export interface UseQASessionOptions {
  /** session id；为 null 时不建连。 */
  sessionId: string | null;
  /** WS 服务器 base，例 "ws://localhost:8000"。默认根据 NEXT_PUBLIC_API_BASE 推导。 */
  wsBase?: string;
  /** 是否自动连接，默认 true。 */
  autoConnect?: boolean;
  /** 透传到 createQAWs。 */
  maxRetries?: number;
  retryDelayMs?: number;
}

export interface UseQASessionResult {
  state: QASessionState;
  status: QAWsStatus;
  /** 派生：剩余 pending 数量。 */
  pendingCount: number;
  /** 派生：剩余可处理（pending + active）数量。 */
  unresolvedCount: number;
  /** 派生：当前 active dialog（== state.dialogs[state.activeDialogId]）。 */
  activeDialog: DialogState | null;
  /** 选中一个学生 dialog 进入 1v1。本地立即切 activeDialogId（乐观）；服务端会回 dialog_active 校验。 */
  selectDialog: (dialogId: string) => void;
  /** 发送师范生消息。本地立即追加到 history（乐观）；isStreaming=true 时调用会被丢弃并 warn。 */
  sendMessage: (dialogId: string, text: string) => void;
  /** 标记 dialog 已解答。 */
  resolve: (
    dialogId: string,
    source?: "teacher_marked" | "self_resolve",
  ) => void;
  /** 放弃 dialog。 */
  abandon: (dialogId: string) => void;
  /** 主动断开（结束陪练）。断开后 status="closed"，service 不再重连。 */
  disconnect: () => void;
  /** 重置 hook 内状态（不影响 ws 连接生命周期）。 */
  resetState: () => void;
}

/**
 * 由 NEXT_PUBLIC_API_BASE 推导 ws:// 或 wss:// base。
 * 若环境变量缺失则默认 ws://localhost:8000。
 */
function deriveDefaultWsBase(): string {
  const httpBase =
    typeof process !== "undefined"
      ? process.env.NEXT_PUBLIC_API_BASE
      : undefined;
  if (!httpBase) return "ws://localhost:8000";
  return httpBase.replace(/^http(s?):\/\//, (_match, secure) =>
    secure ? "wss://" : "ws://",
  );
}

// ============================================================ Hook 实现

export function useQASession(opts: UseQASessionOptions): UseQASessionResult {
  const {
    sessionId,
    wsBase,
    autoConnect = true,
    maxRetries,
    retryDelayMs,
  } = opts;

  const [state, dispatch] = useReducer(reducer, initialState);
  // 状态用 ref 镜像，便于 ws.onclose 重置时不依赖 closure
  const clientRef = useRef<QAWsClient | null>(null);
  const statusRef = useRef<QAWsStatus>("idle");
  const [, forceRender] = useReducer((n: number) => n + 1, 0);

  const url = useMemo(() => {
    if (!sessionId) return null;
    const base = (wsBase ?? deriveDefaultWsBase()).replace(/\/+$/, "");
    return `${base}/ws/qa-sessions/${encodeURIComponent(sessionId)}`;
  }, [sessionId, wsBase]);

  useEffect(() => {
    if (!url) {
      // 没 sessionId：清掉旧连接和状态
      clientRef.current?.close();
      clientRef.current = null;
      statusRef.current = "idle";
      dispatch({ type: "RESET" });
      return;
    }

    const client = createQAWs({
      url,
      maxRetries,
      retryDelayMs,
    });
    clientRef.current = client;

    const offStatus = client.onStatusChange((s) => {
      statusRef.current = s;
      forceRender();
    });

    const offInit = client.on("session_init", (e) => {
      dispatch({
        type: "SESSION_INIT",
        sessionId: e.session_id,
        lesson: e.lesson,
        students: e.students,
        questions: e.questions,
      });
    });
    const offActive = client.on("dialog_active", (e) => {
      dispatch({ type: "DIALOG_ACTIVE", dialogId: e.dialog_id });
    });
    const offChunk = client.on("reply_chunk", (e) => {
      dispatch({ type: "REPLY_CHUNK", dialogId: e.dialog_id, delta: e.delta });
    });
    const offEnd = client.on("reply_end", (e) => {
      dispatch({
        type: "REPLY_END",
        dialogId: e.dialog_id,
        fullContent: e.full_content,
        selfResolved: e.self_resolved,
      });
    });
    const offResolved = client.on("dialog_resolved", (e) => {
      dispatch({
        type: "DIALOG_RESOLVED",
        dialogId: e.dialog_id,
        source: e.source,
      });
    });
    const offAbandoned = client.on("dialog_abandoned", (e) => {
      dispatch({ type: "DIALOG_ABANDONED", dialogId: e.dialog_id });
    });
    const offSummary = client.on("summary", (e) => {
      dispatch({ type: "SUMMARY", data: e.data });
    });
    const offError = client.on("error", (e) => {
      dispatch({ type: "ERROR", error: e });
    });

    if (autoConnect) {
      client.connect();
    }

    return () => {
      offStatus();
      offInit();
      offActive();
      offChunk();
      offEnd();
      offResolved();
      offAbandoned();
      offSummary();
      offError();
      // dev 模式 React StrictMode 双挂载会触发 close → server 端不会误判 replaced
      // 因为新挂载会拿到新 url 但同一 sessionId；服务端会挤旧的，旧 hook 这里又主动 close
      client.close();
      if (clientRef.current === client) {
        clientRef.current = null;
      }
    };
  }, [url, autoConnect, maxRetries, retryDelayMs]);

  // ---- 命令 -----

  const selectDialog = useCallback((dialogId: string) => {
    // 乐观切右侧窗口（即使服务端 dialog_active 还没回，UI 也能立刻响应）
    dispatch({ type: "DIALOG_ACTIVE", dialogId });
    clientRef.current?.send({ type: "select_dialog", dialog_id: dialogId });
  }, []);

  const sendMessage = useCallback((dialogId: string, text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    dispatch({
      type: "TEACHER_MESSAGE_OPTIMISTIC",
      dialogId,
      text: trimmed,
    });
    clientRef.current?.send({
      type: "teacher_message",
      dialog_id: dialogId,
      text: trimmed,
    });
  }, []);

  const resolve = useCallback(
    (
      dialogId: string,
      source: "teacher_marked" | "self_resolve" = "teacher_marked",
    ) => {
      clientRef.current?.send({
        type: "resolve",
        dialog_id: dialogId,
        source,
      });
    },
    [],
  );

  const abandon = useCallback((dialogId: string) => {
    clientRef.current?.send({ type: "abandon", dialog_id: dialogId });
  }, []);

  const disconnect = useCallback(() => {
    clientRef.current?.close();
  }, []);

  const resetState = useCallback(() => {
    dispatch({ type: "RESET" });
  }, []);

  // ---- 派生 -----

  const pendingCount = useMemo(
    () =>
      Object.values(state.dialogs).filter((d) => d.status === "pending").length,
    [state.dialogs],
  );
  const unresolvedCount = useMemo(
    () =>
      Object.values(state.dialogs).filter(
        (d) => d.status === "pending" || d.status === "active",
      ).length,
    [state.dialogs],
  );
  const activeDialog = useMemo<DialogState | null>(() => {
    if (!state.activeDialogId) return null;
    return state.dialogs[state.activeDialogId] ?? null;
  }, [state.activeDialogId, state.dialogs]);

  return {
    state,
    status: statusRef.current,
    pendingCount,
    unresolvedCount,
    activeDialog,
    selectDialog,
    sendMessage,
    resolve,
    abandon,
    disconnect,
    resetState,
  };
}
