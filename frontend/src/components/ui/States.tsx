import type { ReactNode } from "react";
import { AlertTriangle, Loader2, type LucideIcon } from "lucide-react";
import { Button } from "./Button";
import { cx } from "./cx";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-col items-center justify-center px-6 py-10 text-center", className)}>
      <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-[10px] border border-line bg-elevated text-fg-3">
        <Icon size={17} strokeWidth={1.75} aria-hidden />
      </div>
      <p className="text-sm font-medium text-fg">{title}</p>
      {description && <p className="mt-1 max-w-sm text-[13px] text-fg-3">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  children,
  className,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div role="alert" className={cx("rounded-[10px] border border-err/25 bg-err/5 p-4", className)}>
      <div className="flex items-start gap-3">
        <AlertTriangle size={16} strokeWidth={1.75} className="mt-0.5 shrink-0 text-err" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-fg">{title}</p>
          <p className="mt-0.5 text-[13px] break-words text-fg-2">{message}</p>
          {children}
          {onRetry && (
            <Button size="sm" className="mt-3" onClick={onRetry}>
              Try again
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export function LoadingState({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div role="status" className={cx("flex items-center justify-center gap-2 py-10 text-[13px] text-fg-3", className)}>
      <Loader2 size={15} className="spin" aria-hidden />
      {label}
    </div>
  );
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-4" aria-hidden>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="skeleton h-3 flex-1" style={{ maxWidth: `${70 - i * 12}%` }} />
          <div className="skeleton h-3 w-16" />
        </div>
      ))}
    </div>
  );
}
