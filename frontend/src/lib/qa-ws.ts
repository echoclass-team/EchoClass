/**
 * QA 答疑陪练 WebSocket 客户端（框架无关）。
 *
 * 协议：`docs/api_contract.md §3` / `backend/schemas/ws_events.py`。
 * 与 mock server 对接：`uv run python scripts/mock_ws_server.py`
 * → `ws://localhost:8765/ws/qa-sessions/demo-session`
 *
 * 行为约定（来自 `docs/handoff_b_m2.md §B3`）：
 * - 自动重连：断线 3 秒后重试，最多 5 次
 * - 收到 `error{code:"replaced"}` → 不再重连，状态置为 "replaced"
 * - 服务端 `seq` 单调校验：跳号 → console.warn（不 fail）
 * - JSON 解析失败 → console.error 但保连接
 *
 * 设计为框架无关：
 * - 不依赖 React / Zustand
 * - 通过 `on(type, handler)` 注册事件回调
 * - `onStatusChange(handler)` 订阅连接状态
 * - React 集成请见 `hooks/use-qa-session.ts`
 */

import type {
  ClientMessage,
  QAWsStatus,
  ServerMessage,
  ServerMessageOf,
  ServerMessageType,
  WsError,
} from "./qa-ws.types";

export type { QAWsStatus } from "./qa-ws.types";

/** 单类型事件回调签名。 */
export type ServerHandler<T extends ServerMessageType> = (
  event: ServerMessageOf<T>,
) => void;

/** 全量服务端事件回调签名（onAny）。 */
export type AnyServerHandler = (event: ServerMessage) => void;

/** 状态变化回调签名。 */
export type StatusHandler = (status: QAWsStatus) => void;

/** 客户端构造参数。 */
export interface QAWsClientOptions {
  /** WebSocket URL，例：`ws://localhost:8000/ws/qa-sessions/{id}`。 */
  url: string;
  /** 收到 `type:"error"` 帧时回调；不影响连接状态。 */
  onError?: (event: WsError) => void;
  /** 是否启用自动重连，默认 true。 */
  autoReconnect?: boolean;
  /** 最大重试次数，默认 5。 */
  maxRetries?: number;
  /** 每次重试延迟（毫秒），默认 3000。 */
  retryDelayMs?: number;
  /** 注入构造函数（测试 / SSR 用）。默认走全局 WebSocket。 */
  webSocketImpl?: typeof WebSocket;
}

/** WebSocket 客户端公开 API。 */
export interface QAWsClient {
  /** 当前连接状态（同步读取）。 */
  readonly status: QAWsStatus;
  /** 发起首次连接（构造时不会自动 connect）。 */
  connect(): void;
  /** 主动关闭，不再自动重连。 */
  close(): void;
  /** 发送客户端消息。`status !== "open"` 时记录 warn 并丢弃。 */
  send(msg: ClientMessage): void;
  /** 订阅指定 type 的服务端事件，返回 unsubscribe。 */
  on<T extends ServerMessageType>(
    type: T,
    handler: ServerHandler<T>,
  ): () => void;
  /** 订阅全部服务端事件。 */
  onAny(handler: AnyServerHandler): () => void;
  /** 订阅连接状态变化。 */
  onStatusChange(handler: StatusHandler): () => void;
}

/**
 * 创建 1v1 答疑陪练 WebSocket 客户端。
 *
 * 示例：
 * ```ts
 * const ws = createQAWs({ url: "ws://localhost:8765/ws/qa-sessions/demo-session" });
 * ws.on("session_init", (e) => console.log("students:", e.students));
 * ws.on("reply_chunk", (e) => append(e.dialog_id, e.delta));
 * ws.connect();
 * ```
 */
export function createQAWs(options: QAWsClientOptions): QAWsClient {
  return new _QAWsClient(options);
}

// ----------------------------------------------------------------------------
// 实现
// ----------------------------------------------------------------------------

const STATUSES_FINAL = new Set<QAWsStatus>(["closed", "replaced"]);

class _QAWsClient implements QAWsClient {
  private readonly _url: string;
  private readonly _onError?: (event: WsError) => void;
  private readonly _autoReconnect: boolean;
  private readonly _maxRetries: number;
  private readonly _retryDelayMs: number;
  private readonly _WebSocketImpl: typeof WebSocket;

  private _ws: WebSocket | null = null;
  private _status: QAWsStatus = "idle";
  private _retryCount = 0;
  private _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private _deliberatelyClosed = false;
  /** 上一帧 seq；首次为 -1。用于检测跳号。 */
  private _lastSeq = -1;

  private readonly _handlers: Map<
    ServerMessageType,
    Set<(e: ServerMessage) => void>
  > = new Map();
  private readonly _anyHandlers: Set<AnyServerHandler> = new Set();
  private readonly _statusHandlers: Set<StatusHandler> = new Set();

  constructor(opts: QAWsClientOptions) {
    this._url = opts.url;
    this._onError = opts.onError;
    this._autoReconnect = opts.autoReconnect ?? true;
    this._maxRetries = opts.maxRetries ?? 5;
    this._retryDelayMs = opts.retryDelayMs ?? 3000;
    const impl = opts.webSocketImpl ?? (globalThis as { WebSocket?: typeof WebSocket }).WebSocket;
    if (!impl) {
      throw new Error("QAWsClient: no WebSocket implementation available");
    }
    this._WebSocketImpl = impl;
  }

  get status(): QAWsStatus {
    return this._status;
  }

  connect(): void {
    if (STATUSES_FINAL.has(this._status)) {
      console.warn(`[qa-ws] connect() called in final status=${this._status}, ignored`);
      return;
    }
    if (this._status === "connecting" || this._status === "open") {
      return;
    }
    this._open();
  }

  close(): void {
    this._deliberatelyClosed = true;
    this._clearReconnect();
    this._setStatus("closed");
    if (this._ws) {
      try {
        this._ws.close(1000, "client closed");
      } catch (err) {
        console.debug("[qa-ws] close() ws.close threw:", err);
      }
      this._ws = null;
    }
  }

  send(msg: ClientMessage): void {
    if (!this._ws || this._status !== "open") {
      console.warn(`[qa-ws] send() called in status=${this._status}; dropping ${msg.type}`);
      return;
    }
    try {
      this._ws.send(JSON.stringify(msg));
    } catch (err) {
      console.error("[qa-ws] send() failed:", err);
    }
  }

  on<T extends ServerMessageType>(
    type: T,
    handler: ServerHandler<T>,
  ): () => void {
    let bucket = this._handlers.get(type);
    if (!bucket) {
      bucket = new Set();
      this._handlers.set(type, bucket);
    }
    const wrapped = handler as (e: ServerMessage) => void;
    bucket.add(wrapped);
    return () => {
      bucket?.delete(wrapped);
    };
  }

  onAny(handler: AnyServerHandler): () => void {
    this._anyHandlers.add(handler);
    return () => {
      this._anyHandlers.delete(handler);
    };
  }

  onStatusChange(handler: StatusHandler): () => void {
    this._statusHandlers.add(handler);
    return () => {
      this._statusHandlers.delete(handler);
    };
  }

  // ----------------------------------------------------- 内部生命周期

  private _open(): void {
    this._setStatus(this._retryCount > 0 ? "reconnecting" : "connecting");
    this._lastSeq = -1; // 新连接 seq 从 0 重新开始
    let ws: WebSocket;
    try {
      ws = new this._WebSocketImpl(this._url);
    } catch (err) {
      console.error("[qa-ws] WebSocket ctor threw:", err);
      this._scheduleReconnectOrClose();
      return;
    }
    this._ws = ws;

    ws.addEventListener("open", () => {
      this._retryCount = 0;
      this._setStatus("open");
    });

    ws.addEventListener("message", (ev: MessageEvent) => {
      this._onRawMessage(ev.data);
    });

    ws.addEventListener("error", (ev) => {
      // WebSocket error 事件信息很少；详细错误一般在 close 里看 code/reason
      console.warn("[qa-ws] socket error event:", ev);
    });

    ws.addEventListener("close", (ev: CloseEvent) => {
      this._ws = null;
      if (this._deliberatelyClosed) {
        // close() 已处理
        return;
      }
      if (this._status === "replaced") {
        // 收到 replaced 错误后已主动关，不重连
        return;
      }
      console.info(
        `[qa-ws] socket closed: code=${ev.code} reason="${ev.reason}" wasClean=${ev.wasClean}`,
      );
      this._scheduleReconnectOrClose();
    });
  }

  private _scheduleReconnectOrClose(): void {
    if (!this._autoReconnect) {
      this._setStatus("closed");
      return;
    }
    if (this._retryCount >= this._maxRetries) {
      console.warn(
        `[qa-ws] reached max retries (${this._maxRetries}); giving up.`,
      );
      this._setStatus("closed");
      return;
    }
    this._retryCount += 1;
    this._setStatus("reconnecting");
    this._clearReconnect();
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      // 重连前再次确认未被显式 close
      if (this._deliberatelyClosed || STATUSES_FINAL.has(this._status)) {
        return;
      }
      this._open();
    }, this._retryDelayMs);
  }

  private _clearReconnect(): void {
    if (this._reconnectTimer != null) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  }

  private _setStatus(next: QAWsStatus): void {
    if (next === this._status) return;
    this._status = next;
    this._statusHandlers.forEach((h) => {
      try {
        h(next);
      } catch (err) {
        console.error("[qa-ws] status handler threw:", err);
      }
    });
  }

  private _onRawMessage(raw: unknown): void {
    if (typeof raw !== "string") {
      console.error("[qa-ws] non-string frame received; ignoring:", raw);
      return;
    }
    let parsed: ServerMessage;
    try {
      parsed = JSON.parse(raw) as ServerMessage;
    } catch (err) {
      console.error("[qa-ws] JSON parse failed; keeping connection. raw=", raw, err);
      return;
    }
    if (!parsed || typeof parsed !== "object" || typeof (parsed as { type?: unknown }).type !== "string") {
      console.error("[qa-ws] frame missing 'type'; ignoring:", parsed);
      return;
    }

    // seq 单调校验（连接级，全 type 共享）
    const seq = (parsed as { seq?: unknown }).seq;
    if (typeof seq === "number") {
      if (seq !== this._lastSeq + 1 && this._lastSeq !== -1) {
        console.warn(
          `[qa-ws] seq jump: got ${seq}, expected ${this._lastSeq + 1}`,
        );
      }
      // 即使跳号也更新指针，避免后续每帧都 warn
      this._lastSeq = seq;
    }

    // type=error 单独走 onError 钩子；同时也分发给 on("error", ...)
    if (parsed.type === "error") {
      try {
        this._onError?.(parsed);
      } catch (err) {
        console.error("[qa-ws] onError threw:", err);
      }
      // replaced：服务端会主动关连接，本地立即停止重连
      if (parsed.code === "replaced") {
        this._deliberatelyClosed = true;
        this._clearReconnect();
        this._setStatus("replaced");
      }
    }

    this._dispatch(parsed);
  }

  private _dispatch(event: ServerMessage): void {
    const bucket = this._handlers.get(event.type);
    if (bucket) {
      bucket.forEach((h) => {
        try {
          h(event);
        } catch (err) {
          console.error(`[qa-ws] handler for ${event.type} threw:`, err);
        }
      });
    }
    this._anyHandlers.forEach((h) => {
      try {
        h(event);
      } catch (err) {
        console.error("[qa-ws] onAny handler threw:", err);
      }
    });
  }
}
