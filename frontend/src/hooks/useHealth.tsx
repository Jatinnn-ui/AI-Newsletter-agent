import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, errorMessage } from "../lib/api";
import type { HealthResponse } from "../lib/types";

export type Connection = "checking" | "online" | "offline";

interface HealthValue {
  health: HealthResponse | null;
  connection: Connection;
  error: string | null;
  checkedAt: number | null;
  recheck: () => void;
}

const HealthContext = createContext<HealthValue | null>(null);
const INTERVAL_MS = 30000;

/** One shared health check for the whole app, refreshed on an interval and when the tab regains focus. */
export function HealthProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [connection, setConnection] = useState<Connection>("checking");
  const [error, setError] = useState<string | null>(null);
  const [checkedAt, setCheckedAt] = useState<number | null>(null);
  const inflight = useRef<AbortController | null>(null);

  const recheck = useCallback(async () => {
    inflight.current?.abort();
    const ctrl = new AbortController();
    inflight.current = ctrl;
    try {
      const h = await api.health(ctrl.signal);
      setHealth(h);
      setConnection("online");
      setError(null);
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setConnection("offline");
      setError(errorMessage(e));
    } finally {
      if (!ctrl.signal.aborted) setCheckedAt(Date.now());
    }
  }, []);

  useEffect(() => {
    void recheck();
    const t = window.setInterval(() => document.visibilityState === "visible" && void recheck(), INTERVAL_MS);
    const onVis = () => document.visibilityState === "visible" && void recheck();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.clearInterval(t);
      document.removeEventListener("visibilitychange", onVis);
      inflight.current?.abort();
    };
  }, [recheck]);

  return (
    <HealthContext.Provider value={{ health, connection, error, checkedAt, recheck: () => void recheck() }}>
      {children}
    </HealthContext.Provider>
  );
}

export function useHealth() {
  const ctx = useContext(HealthContext);
  if (!ctx) throw new Error("useHealth outside HealthProvider");
  return ctx;
}
