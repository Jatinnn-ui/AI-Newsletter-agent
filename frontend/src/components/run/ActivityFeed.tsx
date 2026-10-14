import { memo, useMemo, useState } from "react";
import { AlertTriangle, Check, ChevronRight, CornerDownRight, FileDown, FileSearch, Globe, Loader2, PenLine, RefreshCcw, ScanSearch, Sparkles, Wrench } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { fmtMs, fmtTime, stageMeta, toolLabel, truncate } from "../../lib/format";
import type { LogEntry, StageName, ToolCallRecord } from "../../lib/types";
import { Segmented } from "../ui/Tabs";
import { cx } from "../ui/cx";
import { EmptyState } from "../ui/States";

function toolIcon(tool: string): LucideIcon {
  const t = tool.toLowerCase();
  if (t.includes("search")) return Globe;
  if (t.includes("retriev") || t.includes("fetch") || t.includes("article")) return FileSearch;
  if (t.includes("summar")) return Sparkles;
  if (t.includes("render") || t.includes("html")) return PenLine;
  if (t.includes("review") || t.includes("critic")) return ScanSearch;
  if (t.includes("revis")) return RefreshCcw;
  if (t.includes("save") || t.includes("storage") || t.includes("file")) return FileDown;
  return Wrench;
}

const statusStyle: Record<ToolCallRecord["status"], { text: string; cls: string }> = {
  running: { text: "Running", cls: "text-info" },
  success: { text: "OK", cls: "text-ok" },
  error: { text: "Error", cls: "text-err" },
  fallback: { text: "Fallback", cls: "text-warn" },
};

export const ToolEventRow = memo(function ToolEventRow({ call }: { call: ToolCallRecord }) {
  const [open, setOpen] = useState(false);
  const Icon = toolIcon(call.tool);
  const s = statusStyle[call.status];
  const summary = call.error ?? call.result_summary ?? call.input_summary;
  return (
    <li className="relative pl-7">
      <span
        aria-hidden
        className={cx(
          "absolute top-0.5 left-0 flex h-5 w-5 items-center justify-center rounded-md border",
          call.status === "error" ? "border-err/30 bg-err/8 text-err" : call.status === "fallback" ? "border-warn/30 bg-warn/8 text-warn" : "border-line-subtle bg-elevated text-fg-2",
        )}
      >
        {call.status === "running" ? <Loader2 size={11} className="spin" /> : <Icon size={11} strokeWidth={1.9} />}
      </span>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="transition-base group -mx-1.5 -my-1 block w-[calc(100%+12px)] rounded-md px-1.5 py-1 text-left hover:bg-elevated/60"
      >
        <div className="flex items-center gap-2">
          <span className="truncate text-[13px] text-fg">{toolLabel(call.tool)}</span>
          <span className={cx("mono text-[11px]", s.cls)}>{s.text}</span>
          <span className="mono ml-auto shrink-0 text-[11px] text-fg-3">{fmtTime(call.started_at)}</span>
          <ChevronRight size={13} className={cx("transition-base shrink-0 text-fg-3", open && "rotate-90")} aria-hidden />
        </div>
        <p className={cx("mt-0.5 text-[12px] leading-snug break-words", call.error ? "text-err/90" : "text-fg-3")}>{truncate(summary, 140)}</p>
      </button>
      {open && (
        <dl className="mono mt-2 mb-1 space-y-1.5 rounded-md border border-line-subtle bg-input p-2.5 text-[11px]">
          <Detail label="input" value={call.input_summary} />
          {call.result_summary && <Detail label="result" value={call.result_summary} />}
          {call.error && <Detail label="error" value={call.error} tone="text-err" />}
          <Detail label="stage" value={call.stage ? (stageMeta[call.stage as StageName]?.label ?? call.stage) : "—"} />
          <Detail label="duration" value={fmtMs(call.duration_ms) ?? (call.status === "running" ? "in progress" : "—")} />
          <Detail label="id" value={call.id} />
        </dl>
      )}
    </li>
  );
});

function Detail({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="grid grid-cols-[64px_1fr] gap-2">
      <dt className="text-fg-3">{label}</dt>
      <dd className={cx("break-words whitespace-pre-wrap", tone ?? "text-fg-2")}>{truncate(value, 600)}</dd>
    </div>
  );
}

const levelCls: Record<LogEntry["level"], string> = {
  info: "text-fg-3",
  running: "text-info",
  success: "text-ok",
  warning: "text-warn",
  error: "text-err",
  approval: "text-accent",
};

function LogRow({ entry }: { entry: LogEntry }) {
  const Icon = entry.level === "error" || entry.level === "warning" ? AlertTriangle : entry.level === "success" ? Check : CornerDownRight;
  return (
    <li className="flex gap-2.5">
      <Icon size={12} strokeWidth={2} className={cx("mt-1 shrink-0", levelCls[entry.level])} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-[12px] leading-snug break-words text-fg-2">{entry.message}</p>
        <p className="mono mt-0.5 text-[10px] text-fg-3">
          {fmtTime(entry.timestamp)}
          {entry.stage && ` · ${entry.stage}`}
        </p>
      </div>
    </li>
  );
}

export function ActivityFeed({ calls, logs, active }: { calls: ToolCallRecord[]; logs: LogEntry[]; active: boolean }) {
  const [view, setView] = useState<"tools" | "log">("tools");
  const sortedCalls = useMemo(() => [...calls].sort((a, b) => b.started_at.localeCompare(a.started_at)), [calls]);
  const sortedLogs = useMemo(() => [...logs].reverse(), [logs]);
  const errors = calls.filter((c) => c.status === "error").length;

  return (
    <div>
      <div className="flex items-center gap-2 px-4 py-3">
        <h2 className="text-[13px] font-medium text-fg">Agent activity</h2>
        <span className="mono text-[11px] text-fg-3">
          {calls.length} tool calls{errors ? ` · ${errors} failed` : ""}
        </span>
        <div className="ml-auto">
          <Segmented
            label="Activity view"
            value={view}
            onChange={setView}
            options={[
              { value: "tools", label: "Tools" },
              { value: "log", label: "Log" },
            ]}
          />
        </div>
      </div>
      <div className="px-4 pb-4">
        {view === "tools" ? (
          sortedCalls.length ? (
            <ol className="space-y-3.5" aria-label="Tool calls, newest first">
              {sortedCalls.map((c) => (
                <ToolEventRow key={c.id} call={c} />
              ))}
            </ol>
          ) : (
            <EmptyState icon={Wrench} title={active ? "Waiting for the first tool call" : "No tool calls recorded"} description={active ? "Searches, retrievals and reviews appear here as they happen." : undefined} className="py-6" />
          )
        ) : sortedLogs.length ? (
          <ol className="space-y-2.5" aria-label="Execution log, newest first">
            {sortedLogs.map((l, i) => (
              <LogRow key={`${l.timestamp}-${i}`} entry={l} />
            ))}
          </ol>
        ) : (
          <EmptyState icon={CornerDownRight} title="No log entries yet" className="py-6" />
        )}
      </div>
    </div>
  );
}
