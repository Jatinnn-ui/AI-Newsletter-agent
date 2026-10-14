import { ChevronRight, FlaskConical } from "lucide-react";
import { fmtDateTime, fmtRelative, modeLabel, stageMeta, truncate } from "../../lib/format";
import { Link, paths } from "../../lib/router";
import { isTerminal, type RunSummary, type StageName } from "../../lib/types";
import { StatusBadge } from "../ui/StatusBadge";
import { cx } from "../ui/cx";

/** Responsive list: a table-like grid on wide screens, stacked rows on mobile. */
export function RunHistoryTable({ runs, compact, subjects }: { runs: RunSummary[]; compact?: boolean; subjects?: Record<string, string> }) {
  return (
    <div role="table" aria-label="Runs" className="w-full">
      {!compact && (
        <div role="rowgroup" className="hidden border-b border-line-subtle px-4 py-2 md:block">
          <div role="row" className="grid grid-cols-[minmax(0,1fr)_132px_128px_132px_16px] gap-3 text-[11px] text-fg-3">
            <span role="columnheader">Goal</span>
            <span role="columnheader">Status</span>
            <span role="columnheader">Mode</span>
            <span role="columnheader">Started</span>
            <span role="columnheader" aria-label="Open" />
          </div>
        </div>
      )}
      <div role="rowgroup">
        {runs.map((r) => {
          const stage = !isTerminal(r.status) && r.current_stage ? stageMeta[r.current_stage as StageName]?.label : null;
          return (
            <Link
              key={r.run_id}
              to={paths.run(r.run_id)}
              role="row"
              className={
                compact
                  ? "transition-base group flex items-center gap-3 border-b border-line-subtle px-4 py-3 last:border-b-0 hover:bg-elevated/50"
                  : "transition-base group grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 border-b border-line-subtle px-4 py-3 last:border-b-0 hover:bg-elevated/50 md:grid-cols-[minmax(0,1fr)_132px_128px_132px_16px]"
              }
            >
              <span role="cell" className="min-w-0 flex-1">
                <span className="block truncate text-[13px] text-fg" title={r.goal}>
                  {truncate(r.goal, 140)}
                </span>
                {subjects?.[r.run_id] && <span className="mt-0.5 block truncate text-[12px] text-fg-2">Subject: {subjects[r.run_id]}</span>}
                <span className="mono mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-fg-3">
                  <span className="shrink-0">{r.run_id.slice(0, 8)}</span>
                  {r.deterministic && (
                    <span className="inline-flex shrink-0 items-center gap-1 text-warn/80">
                      <FlaskConical size={10} aria-hidden /> demo
                    </span>
                  )}
                  {stage && <span className="shrink-0 text-info">· {stage}</span>}
                  {r.error && <span className="min-w-0 truncate text-err/80">· {truncate(r.error, 60)}</span>}
                  <span className={cx("min-w-0 truncate", !compact && "md:hidden")}>
                    · {modeLabel[r.mode]} · {fmtRelative(r.created_at)}
                  </span>
                </span>
              </span>
              <span role="cell">
                <StatusBadge status={r.status} />
              </span>
              {!compact && (
                <>
                  <span role="cell" className="hidden text-[12px] text-fg-2 md:block">
                    {modeLabel[r.mode]}
                  </span>
                  <span role="cell" className="hidden text-[12px] text-fg-2 md:block" title={fmtDateTime(r.created_at)}>
                    {fmtDateTime(r.created_at)}
                  </span>
                </>
              )}
              <span role="cell" className={compact ? "" : "hidden md:block"}>
                <ChevronRight size={15} className="transition-base text-fg-3 opacity-0 group-hover:opacity-100" aria-hidden />
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
