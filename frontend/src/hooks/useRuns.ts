import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../lib/api";
import { isTerminal, type RunDetail, type RunSummary } from "../lib/types";

/** Fetches the run list. Refreshes while any listed run is still active (bounded interval). */
export function useRuns(limit: number) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const ctrl = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    setLoading(true);
    try {
      const data = await api.listRuns(limit, c.signal);
      setRuns(data);
      setError(null);
    } catch (e) {
      if (!c.signal.aborted) setError(errorMessage(e));
    } finally {
      if (!c.signal.aborted) setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    void load();
    return () => ctrl.current?.abort();
  }, [load]);

  const hasActive = runs?.some((r) => !isTerminal(r.status)) ?? false;
  useEffect(() => {
    if (!hasActive) return;
    const t = window.setInterval(() => document.visibilityState === "visible" && void load(), 8000);
    return () => window.clearInterval(t);
  }, [hasActive, load]);

  return { runs, error, loading, reload: load };
}

export interface NewsletterEntry {
  run: RunDetail;
}

const SAVED = new Set(["completed", "completed_with_warnings"]);
const detailCache = new Map<string, RunDetail>();

/**
 * There is no dedicated newsletter index endpoint, so newsletters are derived from saved runs:
 * list runs, then load details for completed runs (cached, since completed runs are immutable).
 */
export function useNewsletters(scanLimit: number, max: number) {
  const { runs, error: listError, loading: listLoading, reload } = useRuns(scanLimit);
  const [items, setItems] = useState<RunDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runs) return;
    let cancelled = false;
    const done = runs.filter((r) => SAVED.has(r.status)).slice(0, max);
    Promise.allSettled(
      done.map(async (r) => {
        const cached = detailCache.get(r.run_id);
        if (cached) return cached;
        const d = await api.getRun(r.run_id);
        if (isTerminal(d.status)) detailCache.set(r.run_id, d);
        return d;
      }),
    ).then((results) => {
      if (cancelled) return;
      const ok = results.flatMap((r) => (r.status === "fulfilled" && r.value.output ? [r.value] : []));
      const failed = results.filter((r) => r.status === "rejected").length;
      setItems(ok);
      setError(failed ? `${failed} newsletter${failed > 1 ? "s" : ""} could not be loaded.` : null);
    });
    return () => {
      cancelled = true;
    };
  }, [runs, max]);

  return {
    items,
    error: listError ?? error,
    loading: listLoading && !items,
    reload,
  };
}
