import { useEffect, useState } from "react";
import { ArrowLeft, FlaskConical, Square } from "lucide-react";
import { fmtDateTime, fmtDuration, modeLabel } from "../../lib/format";
import { Link, paths } from "../../lib/router";
import { isTerminal, type RunDetail } from "../../lib/types";
import type { StreamState } from "../../hooks/useRunStream";
import { Button } from "../ui/Button";
import { Badge, StatusBadge } from "../ui/StatusBadge";
import { CopyButton } from "../studio/NewsletterMetadata";
import { cx } from "../ui/cx";

function useElapsed(start: string, active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [active]);
  return Math.max(0, (now - new Date(start).getTime()) / 1000);
}

const streamText: Record<StreamState, { text: string; cls: string }> = {
  connecting: { text: "connecting", cls: "text-fg-3" },
  live: { text: "live", cls: "text-ok" },
  reconnecting: { text: "reconnecting", cls: "text-warn" },
  polling: { text: "polling", cls: "text-warn" },
  closed: { text: "", cls: "" },
};

export function RunHeader({ run, stream, onCancel }: { run: RunDetail; stream: StreamState; onCancel: () => void }) {
  const terminal = isTerminal(run.status);
  const waiting = run.status === "awaiting_research_approval" || run.status === "awaiting_draft_approval";
  const elapsed = useElapsed(run.created_at, !terminal && !waiting);
  const duration = terminal || waiting ? run.metrics.duration_seconds : elapsed;
  const s = streamText[stream];

  return (
    <header className="pb-5">
      <Link to={paths.history} className="transition-base mb-3 inline-flex items-center gap-1.5 text-[12px] text-fg-3 hover:text-fg">
        <ArrowLeft size={13} aria-hidden /> Run history
      </Link>
      <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1">
          <p className="eyebrow">Run · {modeLabel[run.mode]}</p>
          <h1 className="mt-2 line-clamp-2 text-[22px] leading-snug font-semibold tracking-[-0.02em] text-fg sm:text-[26px]" title={run.goal}>
            {run.plan?.normalized_goal || run.goal}
          </h1>
        </div>
        {!terminal && (
          <Button size="sm" variant="danger" icon={Square} onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-[12px] text-fg-3">
        <StatusBadge status={run.status} />
        {run.deterministic && (
          <Badge tone="warning" title="Offline fixture data, not real research">
            <FlaskConical size={11} aria-hidden /> Demo · fixture data
          </Badge>
        )}
        <span className="inline-flex items-center gap-1">
          <span className="mono">{run.run_id.slice(0, 12)}</span>
          <CopyButton text={run.run_id} label="Copy run ID" />
        </span>
        <span>Started {fmtDateTime(run.created_at)}</span>
        <span className="mono">{waiting ? "paused · " : ""}{fmtDuration(duration)}</span>
        {s.text && (
          <span className={cx("mono inline-flex items-center gap-1.5", s.cls)} title="Event stream connection">
            <span aria-hidden className={cx("h-1.5 w-1.5 rounded-full bg-current", stream === "live" && "pulse")} />
            {s.text}
          </span>
        )}
      </div>
    </header>
  );
}
