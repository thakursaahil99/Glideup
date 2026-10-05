"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

import { ApiError, errorMessage } from "@/lib/api/client";
import { fetchTicket } from "@/lib/api/interviews";
import type { InterviewDetail, InterviewMessage, InterviewState } from "@/lib/api/types";

export type Connection = "connecting" | "open" | "reconnecting" | "closed";

export type RoomState = {
  interview: InterviewState | null;
  typeName: string;
  messages: InterviewMessage[];
  /** The interviewer reply currently streaming in, token by token. */
  streaming: { id: string; kind: string; text: string } | null;
  /** An action is in flight; inputs stay disabled until the server finishes it. */
  busy: boolean;
  connection: Connection;
  error: string | null;
};

/** Everything the server can send (see the WebSocket docs in app/api/v1/interviews.py). */
export type ServerEvent =
  | ({ type: "state"; busy: boolean } & InterviewDetail)
  | { type: "message"; message: InterviewMessage }
  | { type: "stream_start"; id: string; kind: string }
  | { type: "delta"; id: string; text: string }
  | { type: "stream_end"; message: InterviewMessage }
  | { type: "interview"; interview: InterviewState }
  | { type: "ended"; interview: InterviewState }
  | { type: "error"; code: string; message: string }
  | { type: "pong" };

type LocalEvent =
  | { type: "connection"; value: Connection; error?: string | null }
  | { type: "sending" }
  | { type: "local_error"; message: string };

export function initialRoomState(detail?: InterviewDetail): RoomState {
  return {
    interview: detail?.interview ?? null,
    typeName: detail?.type_name ?? "",
    messages: detail?.messages ?? [],
    streaming: null,
    busy: false,
    connection: "connecting",
    error: null,
  };
}

function withMessage(messages: InterviewMessage[], message: InterviewMessage) {
  return messages.some((m) => m.id === message.id)
    ? messages
    : [...messages, message].sort((a, b) => a.seq - b.seq);
}

export function roomReducer(state: RoomState, event: ServerEvent | LocalEvent): RoomState {
  switch (event.type) {
    case "state":
      return {
        ...state,
        interview: event.interview,
        typeName: event.type_name,
        messages: event.messages,
        streaming: null,
        busy: event.busy,
        error: null,
      };
    case "message":
      return { ...state, messages: withMessage(state.messages, event.message) };
    case "stream_start":
      return { ...state, streaming: { id: event.id, kind: event.kind, text: "" } };
    case "delta":
      return state.streaming?.id === event.id
        ? { ...state, streaming: { ...state.streaming, text: state.streaming.text + event.text } }
        : state;
    case "stream_end":
      return { ...state, streaming: null, messages: withMessage(state.messages, event.message) };
    case "interview":
      return { ...state, interview: event.interview, busy: false };
    case "ended":
      return { ...state, interview: event.interview, busy: false, streaming: null };
    case "error":
      return { ...state, busy: false, error: event.message };
    case "pong":
      return state;
    case "connection":
      return {
        ...state,
        connection: event.value,
        error: event.error === undefined ? state.error : event.error,
        // A dropped connection ends any half-shown stream; the transcript arrives on reconnect.
        ...(event.value === "open" ? {} : { busy: false, streaming: null }),
      };
    case "sending":
      return { ...state, busy: true, error: null };
    case "local_error":
      return { ...state, error: event.message };
  }
}

const PING_MS = 25_000;
const MAX_BACKOFF_MS = 10_000;

export function newClientId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function useInterviewRoom(id: string, initial?: InterviewDetail) {
  const [state, dispatch] = useReducer(roomReducer, initial, initialRoomState);
  const socket = useRef<WebSocket | null>(null);
  const finished = useRef(initial?.interview.status === "completed");
  const status = state.interview?.status;

  useEffect(() => {
    if (status === "completed") finished.current = true;
  }, [status]);

  useEffect(() => {
    let stopped = false;
    let attempts = 0;
    let timer: number | undefined;

    function retry(message: string) {
      if (stopped || finished.current) return;
      attempts += 1;
      dispatch({ type: "connection", value: "reconnecting", error: message });
      timer = window.setTimeout(() => void connect(), Math.min(MAX_BACKOFF_MS, 500 * 2 ** attempts));
    }

    async function connect() {
      if (stopped || finished.current) return;
      dispatch({ type: "connection", value: attempts ? "reconnecting" : "connecting" });
      let ticket: Awaited<ReturnType<typeof fetchTicket>>;
      try {
        ticket = await fetchTicket(id);
      } catch (error) {
        // A closed interview (409) or a missing one (404) won't get better by retrying.
        if (error instanceof ApiError && (error.status === 409 || error.status === 404)) {
          dispatch({ type: "connection", value: "closed", error: errorMessage(error) });
          return;
        }
        retry(errorMessage(error));
        return;
      }
      if (stopped) return;
      const ws = new WebSocket(`${ticket.url}?ticket=${encodeURIComponent(ticket.ticket)}`);
      socket.current = ws;
      ws.onopen = () => {
        attempts = 0;
        dispatch({ type: "connection", value: "open", error: null });
      };
      ws.onmessage = (message) => {
        try {
          const event = JSON.parse(String(message.data)) as ServerEvent;
          if (event.type === "ended") finished.current = true;
          dispatch(event);
        } catch {
          // ignore malformed frames
        }
      };
      ws.onclose = () => {
        if (socket.current === ws) socket.current = null;
        if (stopped || finished.current) {
          dispatch({ type: "connection", value: "closed" });
          return;
        }
        retry("Connection lost. Reconnecting…");
      };
    }

    void connect();
    const ping = window.setInterval(() => {
      if (socket.current?.readyState === WebSocket.OPEN) {
        socket.current.send(JSON.stringify({ type: "ping" }));
      }
    }, PING_MS);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      window.clearInterval(ping);
      socket.current?.close(1000);
      socket.current = null;
    };
  }, [id]);

  const send = useCallback((event: Record<string, unknown>) => {
    const ws = socket.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      dispatch({ type: "local_error", message: "Not connected yet. Please wait a moment." });
      return false;
    }
    ws.send(JSON.stringify(event));
    dispatch({ type: "sending" });
    return true;
  }, []);

  return {
    state,
    start: () => send({ type: "start" }),
    answer: (text: string, attachment?: string) =>
      send({ type: "answer", text, attachment: attachment || null, client_id: newClientId() }),
    hint: () => send({ type: "hint" }),
    skip: () => send({ type: "skip" }),
    end: () => send({ type: "end" }),
  };
}
