import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, errorMessage } from "../lib/api";
import { isTerminal, type RunDetail } from "../lib/types";

export type StreamState = "connecting" | "live" | "reconnecting" | "polling" | "closed";

const REFRESH_EVENTS = new Set(["log", "tool_call", "stage", "status", "artifact"]);
const POLL_MS = 4000;
const MAX_BACKOFF_MS = 15000;
const SSE_FAILURES_BEFORE_POLLING = 4;

/**
 * Loads a run and keeps it current from the backend's SSE stream (fetch-based so the
 * optional access token travels in a header). Each SSE event triggers a debounced
 * refetch of the run detail, so the UI only ever shows server state.
 *
 * One effect owns one loop per run id. Terminal states and unmount stop everything.
 * If the stream keeps failing, it falls back to bounded polling of GET /runs/{id}.
 */
export function useRunStream(runId: string) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [stream, setStream] = useState<StreamState>("connecting");

  const inflight = useRef(false);
  const queued = useRef(false);
  const debounce = useRef<number | null>(null);
  const terminal = useRef(false);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    if (inflight.current) {
      queued.current = true;
      return;
    }
    inflight.current = true;
    try {
      const detail = await api.getRun(runId);
      if (!alive.current || detail.run_id !== runId) return;
      terminal.current = isTerminal(detail.status);
      setRun(detail);
      setError(null);
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e : new Error(errorMessage(e)));
    } finally {
      inflight.current = false;
      if (queued.current && alive.current) {
        queued.current = false;
        void refresh();
      }
    }
  }, [runId]);

  /** Apply a RunDetail returned by an action endpoint immediately. */
  const apply = useCallback((detail: RunDetail) => {
    terminal.current = isTerminal(detail.status);
    setRun(detail);
  }, []);

  useEffect(() => {
    alive.current = true;
    terminal.current = false;
    setRun(null);
    setError(null);
    setStream("connecting");

    const controller = new AbortController();
    let cursor = 0;
    let failures = 0;
    const sleep = (ms: number) =>
      new Promise<void>((resolve) => {
        const t = window.setTimeout(resolve, ms);
        controller.signal.addEventListener("abort", () => {
          window.clearTimeout(t);
          resolve();
        });
      });
    const schedule = () => {
      if (debounce.current !== null) return;
      debounce.current = window.setTimeout(() => {
        debounce.current = null;
        void refresh();
      }, 150);
    };

    async function readStream(): Promise<"ended" | "dropped"> {
      const res = await api.events(runId, cursor, controller.signal);
      if (!res.body) throw new Error("Streaming not supported by this browser.");
      setStream("live");
      failures = 0;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          if (!block.trim() || block.startsWith(":")) continue;
          let event = "message";
          for (const line of block.split(/\r?\n/)) {
            if (line.startsWith("id:")) cursor = Number(line.slice(3).trim()) || cursor;
            else if (line.startsWith("event:")) event = line.slice(6).trim();
          }
          if (event === "end") {
            reader.cancel().catch(() => undefined);
            return "ended";
          }
          if (REFRESH_EVENTS.has(event)) schedule();
        }
        if (done) return "dropped";
      }
    }

    async function loop() {
      await refresh();
      while (!controller.signal.aborted && !terminal.current) {
        if (failures >= SSE_FAILURES_BEFORE_POLLING) {
          // Bounded polling fallback: one request at a time, fixed interval, stops at terminal.
          setStream("polling");
          await sleep(POLL_MS);
          if (controller.signal.aborted) return;
          await refresh();
          continue;
        }
        try {
          const outcome = await readStream();
          await refresh();
          if (outcome === "ended") break;
          // Server closed the stream without "end" (e.g. timeout): reconnect from cursor.
        } catch (e) {
          if (controller.signal.aborted) return;
          if (e instanceof ApiError && (e.status === 401 || e.status === 404)) {
            setError(e);
            break;
          }
          failures++;
          setStream("reconnecting");
          await sleep(Math.min(1000 * 2 ** failures, MAX_BACKOFF_MS));
          if (!controller.signal.aborted) await refresh();
        }
      }
      if (!controller.signal.aborted) setStream("closed");
    }

    void loop();
    return () => {
      alive.current = false;
      controller.abort();
      if (debounce.current !== null) window.clearTimeout(debounce.current);
      debounce.current = null;
    };
  }, [runId, refresh]);

  return { run, error, stream, refresh, apply };
}
