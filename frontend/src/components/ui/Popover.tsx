import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { cx } from "./cx";

/**
 * Lightweight anchored popover. Closes on outside click, Escape and focus leaving the
 * popover. Positioned relative to the trigger wrapper; aligned to the end edge by default.
 */
export function Popover({
  trigger,
  children,
  align = "end",
  label,
  panelClassName,
}: {
  trigger: (props: { open: boolean; toggle: () => void; id: string }) => ReactNode;
  children: ReactNode | ((close: () => void) => ReactNode);
  align?: "start" | "end";
  label?: string;
  panelClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const close = () => setOpen(false);

  return (
    <div ref={wrap} className="relative">
      {trigger({ open, toggle: () => setOpen((o) => !o), id })}
      {open && (
        <div
          id={id}
          role="dialog"
          aria-label={label}
          className={cx(
            "fade-in absolute top-[calc(100%+6px)] z-30 w-[min(320px,calc(100vw-32px))] rounded-[10px] border border-line bg-elevated p-3 shadow-[0_16px_40px_-16px_rgba(0,0,0,0.65)]",
            align === "end" ? "right-0" : "left-0",
            panelClassName,
          )}
        >
          {typeof children === "function" ? children(close) : children}
        </div>
      )}
    </div>
  );
}
