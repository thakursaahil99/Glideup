import { describe, expect, it } from "vitest";

import { initialRoomState, readEventStream, roomReducer, type ServerEvent } from "@/lib/interview-room";

function streamOf(...chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body);
}

describe("HTTP interview transport", () => {
  it("reads NDJSON events even when lines are split across chunks", async () => {
    const seen: ServerEvent[] = [];
    await readEventStream(
      streamOf('{"type":"stream_start","id":"m1","kind":"follow_up"}\n{"type":"del', 'ta","id":"m1","text":"Hi"}\n', '{"type":"pong"}'),
      (event) => seen.push(event),
    );
    expect(seen.map((e) => e.type)).toEqual(["stream_start", "delta", "pong"]);
  });

  it("clears a stuck action when a request ends without a closing event", () => {
    const busy = roomReducer(initialRoomState(), { type: "sending" });
    expect(busy.busy).toBe(true);
    expect(roomReducer(busy, { type: "idle" }).busy).toBe(false);
  });
});
