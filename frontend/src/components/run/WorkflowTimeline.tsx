import { memo, useState } from "react";
import { Check, ChevronDown, Circle, CircleDashed, Hand, Loader2, Minus, X } from "lucide-react";
import { fmtDuration, stageMeta, STAGES } from "../../lib/format";
import type { LogEntry, RunDetail, StageName, StageStatus } from "../../lib/types";
import { cx } from "../ui/cx";

const STATUS_TEXT: Record<StageStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  waiting: "Waiting for approval",
  skipped: "Skipped",
  cancelled: "Cancelled",
};

function StageIcon({ status, size = "md" }: { status: StageStatus; size?: "sm" | "md" }) {
  const base = cx("flex shrink-0 items-center justify-center rounded-full", size === "sm" ? "h-4 w-4" : "h-5 w-5");
  const ic = size === "sm" ? 10 : 12;
  switch (status) {
    case "completed":
      return (
        <span className={cx(base, "bg-ok/12 text-ok")}>
          <Check size={ic} strokeWidth={2.5} aria-hidden />
        </span>
      );
    case "running":
      return (
        <span className={cx(base, "bg-info/12 text-info")}>
          <Loader2 size={ic} strokeWidth={2.25} className="spin" aria-hidden />
        </span>
      );
    case "waiting":
      return (
        <span className={cx(base, "bg-accent-soft text-accent ring-1 ring-accent/40")}>
          <Hand size={ic - 1} strokeWidth={2} aria-hidden />
        </span>
      );
    case "failed":
      return (
        <span className={cx(base, "bg-err/12 text-err")}>
          <X size={ic} strokeWidth={2.5} aria-hidden />
        </span>
      );
    case "skipped":
      return (
        <span className={cx(base, "text-fg-3")}>
          <Minus size={ic} strokeWidth={2} aria-hidden />
        </span>
      );
    case "cancelled":
      return (
        <span className={cx(base, "text-fg-3")}>
          <CircleDashed size={ic + 1} strokeWidth={1.75} aria-hidden />
        </span>
      );
    default:
      return (
        <span className={cx(base, "text-line")}>
          <Circle size={ic + 1} strokeWidth={1.75} aria-hidden />
        </span>
      );
  }
}

/** Duration per stage, from the timestamps of that stage's own log entries (server time). */
function stageDurations(logs: LogEntry[]): Partial<Record<StageName, number>> {
  const span: Partial<Record<StageName, [number, number]>> = {};
  for (const l of logs) {
    if (!l.stage) continue;
    const t = new Date(l.timestamp).getTime();
    if (Number.isNaN(t)) continue;
    const s = span[l.stage as StageName];
    span[l.stage as StageName] = s ? [Math.min(s[0], t), Math.max(s[1], t)] : [t, t];
  }
  const out: Partial<Record<StageName, number>> = {};
  for (const [k, [a, b]] of Object.entries(span) as [StageName, [number, number]][]) if (b > a) out[k] = (b - a) / 1000;
  return out;
}

function skippedNote(stage: StageName, run: RunDetail) {
  if (stage === "revision") return run.review?.passed ? "Not needed: review passed." : "Not required.";
  return null;
}

/** Stages to display: hide revision until it has actually been reached. */
function visibleStages(run: RunDetail): StageName[] {
  return STAGES.filter((s) => s !== "revision" || (run.stages.revision ?? "pending") !== "pending" || run.revisions.length > 0);
}

/** Short labels keep the horizontal strip compact. */
const SHORT_LABEL: Partial<Record<StageName, string>> = {
  planning: "Plan",
  research: "Research",
  selection: "Select",
  summarization: "Summarize",
  writing: "Write",
  review: "Review",
  revision: "Revise",
  output: "Output",
};

/**
 * Compact horizontal stage indicator. Collapsed by default; expands to the detailed
 * timeline. State is derived entirely from the backend's stage map and logs, never timers.
 */
export const WorkflowStrip = memo(function WorkflowStrip({ run }: { run: RunDetail }) {
  const [open, setOpen] = useState(false);
  const stages = visibleStages(run);
  const durations = stageDurations(run.logs);
  const done = stages.filter((s) => (run.stages[s] ?? "pending") === "completed").length;
  const activeStage = stages.find((s) => ["running", "waiting"].includes(run.stages[s] ?? "")) ?? null;

  return (
    <div className="panel w-full overflow-hidden">
      <div className="flex w-full min-w-0 items-center gap-3 px-3 py-2.5">
        <ol className="flex w-0 min-w-0 flex-1 items-center gap-1 overflow-x-auto" aria-label="Workflow stages">
          {stages.map((stage, i) => {
            const status = (run.stages[stage] ?? "pending") as StageStatus;
            const activeStep = status === "running" || status === "waiting";
            return (
              <li key={stage} className="flex shrink-0 items-center gap-1" aria-current={activeStep ? "step" : undefined}>
                <span
                  className={cx(
                    "flex items-center gap-1.5 rounded-full px-1.5 py-1",
                    activeStep && "bg-elevated",
                  )}
                  title={`${stageMeta[stage].label}: ${STATUS_TEXT[status]}`}
                >
                  <StageIcon status={status} size="sm" />
                  <span className={cx("hidden text-[12px] whitespace-nowrap sm:inline", status === "pending" ? "text-fg-3" : activeStep ? "font-medium text-fg" : "text-fg-2")}>
                    {SHORT_LABEL[stage]}
                  </span>
                  <span className="sr-only">: {STATUS_TEXT[status]}</span>
                </span>
                {i < stages.length - 1 && <span aria-hidden className={cx("h-px w-3 shrink-0 sm:w-4", status === "completed" ? "bg-ok/40" : "bg-line-subtle")} />}
              </li>
            );
          })}
        </ol>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="transition-base flex shrink-0 items-center gap-1 rounded-[7px] px-2 py-1 text-[12px] text-fg-3 hover:bg-elevated hover:text-fg"
        >
          <span className="mono hidden md:inline">
            {activeStage ? stageMeta[activeStage].label : `${done}/${stages.length}`}
          </span>
          <span className="md:hidden">Details</span>
          <ChevronDown size={14} className={cx("transition-base", open && "rotate-180")} aria-hidden />
        </button>
      </div>
      {open && (
        <div className="fade-in border-t border-line-subtle px-4 py-3">
          <WorkflowTimeline run={run} durations={durations} />
        </div>
      )}
    </div>
  );
});

export const WorkflowTimeline = memo(function WorkflowTimeline({ run, durations }: { run: RunDetail; durations?: Partial<Record<StageName, number>> }) {
  const dur = durations ?? stageDurations(run.logs);
  const stages = visibleStages(run);

  return (
    <ol className="relative" aria-label="Workflow stages">
      {stages.map((stage, i) => {
        const status = (run.stages[stage] ?? "pending") as StageStatus;
        const meta = stageMeta[stage];
        const last = i === stages.length - 1;
        const d = status === "completed" ? dur[stage] : undefined;
        const note = status === "skipped" ? skippedNote(stage, run) : null;
        const revisions = stage === "revision" ? run.revisions.length : 0;
        return (
          <li key={stage} className="relative flex gap-3 pb-4 last:pb-0" aria-current={status === "running" || status === "waiting" ? "step" : undefined}>
            {!last && (
              <span aria-hidden className={cx("absolute top-6 bottom-0 left-[9.5px] w-px", status === "completed" ? "bg-ok/30" : "bg-line-subtle")} />
            )}
            <StageIcon status={status} />
            <div className="-mt-px min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <span className={cx("text-[13px]", status === "pending" ? "text-fg-3" : "text-fg", (status === "running" || status === "waiting") && "font-medium")}>{meta.label}</span>
                <span className="sr-only">: {STATUS_TEXT[status]}</span>
                {revisions > 0 && <span className="mono text-[11px] text-fg-3">×{revisions}</span>}
                <span className="mono ml-auto shrink-0 text-[11px] text-fg-3">
                  {d != null ? fmtDuration(d) : status === "waiting" ? <span className="text-accent">awaiting you</span> : status === "running" ? <span className="text-info">running</span> : status === "failed" ? <span className="text-err">failed</span> : null}
                </span>
              </div>
              <p className="mt-0.5 text-[12px] leading-snug text-fg-3">{note ?? meta.description}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
});
