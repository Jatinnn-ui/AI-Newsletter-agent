import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { cx } from "./cx";

type ToastTone = "success" | "error" | "info";
interface Toast {
  id: number;
  tone: ToastTone;
  title: string;
  description?: string;
}

const ToastContext = createContext<((t: Omit<Toast, "id">) => void) | null>(null);

const icons = { success: CheckCircle2, error: AlertTriangle, info: Info };
const colors = { success: "text-ok", error: "text-err", info: "text-info" };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);

  const dismiss = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (t: Omit<Toast, "id">) => {
      const id = ++seq.current;
      setToasts((ts) => [...ts.slice(-3), { ...t, id }]);
      window.setTimeout(() => dismiss(id), t.tone === "error" ? 8000 : 4500);
    },
    [dismiss],
  );
  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {toasts.length > 0 && (
        <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-[min(360px,calc(100vw-2rem))] max-w-[calc(100vw-2rem)] flex-col gap-2">
          {/* Separate live regions so errors interrupt and confirmations don't. */}
          <div aria-live="polite" className="contents">
            {toasts.filter((t) => t.tone !== "error").map((t) => <ToastItem key={t.id} t={t} onDismiss={dismiss} />)}
          </div>
          <div aria-live="assertive" className="contents">
            {toasts.filter((t) => t.tone === "error").map((t) => <ToastItem key={t.id} t={t} onDismiss={dismiss} />)}
          </div>
        </div>
      )}
    </ToastContext.Provider>
  );
}

function ToastItem({ t, onDismiss }: { t: Toast; onDismiss: (id: number) => void }) {
  const Icon = icons[t.tone];
  return (
    <div role={t.tone === "error" ? "alert" : "status"} className="fade-in pointer-events-auto flex items-start gap-3 rounded-[10px] border border-line bg-elevated px-3.5 py-3 shadow-[0_12px_32px_-12px_rgba(0,0,0,0.6)]">
      <Icon size={16} strokeWidth={1.75} className={cx("mt-0.5 shrink-0", colors[t.tone])} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium text-fg">{t.title}</p>
        {t.description && <p className="mt-0.5 text-[12px] break-words text-fg-2">{t.description}</p>}
      </div>
      <button type="button" aria-label="Dismiss notification" onClick={() => onDismiss(t.id)} className="transition-base -mr-1 rounded p-0.5 text-fg-3 hover:text-fg">
        <X size={14} aria-hidden />
      </button>
    </div>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast outside ToastProvider");
  return ctx;
}
