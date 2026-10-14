import { statusLabel } from "../../lib/format";
import type { RunStatus } from "../../lib/types";
import { cx } from "./cx";

export type Tone = "neutral" | "accent" | "success" | "warning" | "error" | "info";

const tones: Record<Tone, string> = {
  neutral: "text-fg-2 bg-elevated border-line",
  accent: "text-accent bg-accent-soft border-accent/30",
  success: "text-ok bg-ok/12 border-ok/30",
  warning: "text-warn bg-warn/12 border-warn/30",
  error: "text-err bg-err/12 border-err/30",
  info: "text-info bg-info/12 border-info/30",
};

const dot: Record<Tone, string> = {
  neutral: "bg-fg-3",
  accent: "bg-accent",
  success: "bg-ok",
  warning: "bg-warn",
  error: "bg-err",
  info: "bg-info",
};

export function Badge({ tone = "neutral", children, live, className, title }: { tone?: Tone; children: React.ReactNode; live?: boolean; className?: string; title?: string }) {
  return (
    <span
      title={title}
      className={cx("inline-flex h-[22px] shrink-0 items-center gap-1.5 rounded-full border px-2 text-[12px] font-medium leading-none whitespace-nowrap", tones[tone], className)}
    >
      <span aria-hidden className={cx("h-1.5 w-1.5 rounded-full", dot[tone], live && "pulse")} />
      {children}
    </span>
  );
}

export const statusTone: Record<RunStatus, Tone> = {
  queued: "neutral",
  running: "info",
  awaiting_research_approval: "accent",
  awaiting_draft_approval: "accent",
  completed: "success",
  completed_with_warnings: "warning",
  failed: "error",
  cancelled: "neutral",
  expired: "neutral",
};

export function StatusBadge({ status, className }: { status: RunStatus; className?: string }) {
  return (
    <Badge tone={statusTone[status]} live={status === "running" || status === "queued"} className={className}>
      {statusLabel[status]}
    </Badge>
  );
}
