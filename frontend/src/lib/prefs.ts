import { useCallback, useSyncExternalStore } from "react";
import type { ExecutionMode } from "./types";

// Frontend-only preferences, stored in this browser's localStorage. They prefill the goal
// composer. They are not server configuration and contain no secrets.

export interface Preferences {
  mode: ExecutionMode;
  articleCount: number | null; // null = let the planner decide (backend default 5)
  lookbackDays: number | null; // null = backend default 7
  topic: string;
  audience: string;
  sidebarCollapsed: boolean;
}

export const DEFAULT_PREFS: Preferences = {
  mode: "autonomous",
  articleCount: 5,
  lookbackDays: 7,
  topic: "",
  audience: "",
  sidebarCollapsed: false,
};

const KEY = "newsletter-agent-prefs-v1";
const listeners = new Set<() => void>();
let cache: Preferences | null = null;

function read(): Preferences {
  if (cache) return cache;
  try {
    const raw = localStorage.getItem(KEY);
    cache = { ...DEFAULT_PREFS, ...(raw ? (JSON.parse(raw) as Partial<Preferences>) : {}) };
  } catch {
    cache = { ...DEFAULT_PREFS };
  }
  return cache;
}

function write(next: Preferences) {
  cache = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable: keep in memory */
  }
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

export function usePreferences() {
  const prefs = useSyncExternalStore(subscribe, read, read);
  const update = useCallback((patch: Partial<Preferences>) => write({ ...read(), ...patch }), []);
  const reset = useCallback(() => write({ ...DEFAULT_PREFS, sidebarCollapsed: read().sidebarCollapsed }), []);
  return { prefs, update, reset };
}
