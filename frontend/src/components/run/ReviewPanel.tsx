import { useState } from "react";
import { AlertOctagon, AlertTriangle, Check, ChevronRight, Info, RefreshCcw, ScanSearch, X } from "lucide-react";
import { fmtDateTime } from "../../lib/format";
import type { ReviewIssue, ReviewResult, RevisionRecord } from "../../lib/types";
import { Badge } from "../ui/StatusBadge";
import { cx } from "../ui/cx";
import { EmptyState } from "../ui/States";

export function ReviewScore({ review }: { review: ReviewResult }) {
  const critical = review.issues.filter((i) => i.severity === "critical").length;
  const tone = review.passed ? "bg-ok" : critical ? "bg-err" : "bg-warn";
  return (
    <div>
      <div className="flex items-end gap-3">
        <p className="leading-none">
          <span className="mono text-[32px] font-medium tracking-[-0.03em] text-fg">{review.score}</span>
          <span className="mono text-[13px] text-fg-3">/100</span>
        </p>
        <div className="mb-0.5 ml-auto">
          {review.passed ? <Badge tone="success">Passed</Badge> : <Badge tone={critical ? "error" : "warning"}>Needs improvement</Badge>}
        </div>
      </div>
      <div
        className="relative mt-3 h-1.5 rounded-full bg-elevated"
        role="meter"
        aria-label="Review score"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={review.score}
        aria-valuetext={`${review.score} of 100, pass threshold ${review.threshold}`}
      >
        <div className={cx("h-full rounded-full", tone)} style={{ width: `${review.score}%` }} />
        <span aria-hidden className="absolute -top-1 h-3.5 w-px bg-fg-2" style={{ left: `${review.threshold}%` }} title={`Pass threshold ${review.threshold}`} />
      </div>
      <p className="mono mt-2 text-[11px] text-fg-3">
        threshold {review.threshold} · attempt {review.attempt} · {review.reviewer} · {fmtDateTime(review.reviewed_at)}
      </p>
    </div>
  );
}

export function ReviewChecklist({ review }: { review: ReviewResult }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <ul className="divide-y divide-line-subtle" aria-label="Validation checks">
      {review.checks.map((c) => {
        const expanded = open === c.id;
        return (
          <li key={c.id}>
            <button
              type="button"
              aria-expanded={expanded}
              onClick={() => setOpen(expanded ? null : c.id)}
              className="transition-base flex w-full items-center gap-2.5 py-2 text-left hover:text-fg"
            >
              {c.passed ? <Check size={14} strokeWidth={2.25} className="shrink-0 text-ok" aria-label="Passed" /> : <X size={14} strokeWidth={2.25} className="shrink-0 text-err" aria-label="Failed" />}
              <span className="min-w-0 flex-1 truncate text-[13px] text-fg-2">{c.label}</span>
              <span className="mono text-[11px] text-fg-3">{c.score}</span>
              <ChevronRight size={13} className={cx("transition-base shrink-0 text-fg-3", expanded && "rotate-90")} aria-hidden />
            </button>
            {expanded && <p className="pb-2.5 pl-6 text-[12px] leading-relaxed text-fg-3">{c.details} <span className="mono">(weight {c.weight})</span></p>}
          </li>
        );
      })}
    </ul>
  );
}

const sevMeta = {
  critical: { icon: AlertOctagon, cls: "text-err", label: "Critical" },
  major: { icon: AlertTriangle, cls: "text-warn", label: "Major" },
  minor: { icon: Info, cls: "text-fg-3", label: "Minor" },
};

function IssueRow({ issue }: { issue: ReviewIssue }) {
  const m = sevMeta[issue.severity];
  const Icon = m.icon;
  return (
    <li className="flex gap-2.5 py-2">
      <Icon size={14} strokeWidth={1.9} className={cx("mt-0.5 shrink-0", m.cls)} aria-hidden />
      <div className="min-w-0">
        <p className="text-[13px] leading-snug text-fg">
          <span className={cx("mono mr-1.5 text-[10px] tracking-wide uppercase", m.cls)}>{m.label}</span>
          {issue.message}
        </p>
        {issue.suggestion && <p className="mt-0.5 text-[12px] leading-snug text-fg-3">Suggestion: {issue.suggestion}</p>}
      </div>
    </li>
  );
}

export function RevisionHistory({ revisions }: { revisions: RevisionRecord[] }) {
  if (!revisions.length) return null;
  return (
    <ol className="space-y-2.5">
      {revisions.map((r, i) => (
        <li key={`${r.attempt}-${i}`} className="rounded-[8px] border border-line-subtle bg-input p-3">
          <div className="flex items-center gap-2 text-[12px]">
            <RefreshCcw size={12} className="text-fg-3" aria-hidden />
            <span className="text-fg">Revision {i + 1}</span>
            <span className="text-fg-3">{r.trigger === "user" ? "requested by you" : "requested by reviewer"}</span>
            {r.score_before != null && r.score_after != null && (
              <span className="mono ml-auto text-[11px] text-fg-3">
                {r.score_before} → {r.score_after}
              </span>
            )}
          </div>
          {r.feedback && <p className="mt-1.5 text-[12px] text-fg-2">“{r.feedback}”</p>}
          {r.changes.length > 0 && (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[12px] text-fg-3">
              {r.changes.slice(0, 6).map((c, j) => (
                <li key={j}>{c}</li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}

export function ReviewPanel({ review, revisions, pending }: { review: ReviewResult | null; revisions: RevisionRecord[]; pending: boolean }) {
  if (!review) {
    return <EmptyState icon={ScanSearch} title={pending ? "Review not run yet" : "No review recorded"} description={pending ? "The self-review runs after the newsletter draft is written." : undefined} className="py-8" />;
  }
  const critical = review.issues.filter((i) => i.severity === "critical");
  const others = review.issues.filter((i) => i.severity !== "critical");
  return (
    <div className="space-y-5">
      <ReviewScore review={review} />
      {critical.length > 0 && (
        <div role="alert" className="rounded-[8px] border border-err/30 bg-err/5 px-3 py-2">
          <p className="text-[12px] font-medium text-err">
            {critical.length} critical {critical.length === 1 ? "issue" : "issues"}: the draft cannot pass review regardless of score.
          </p>
          <ul className="divide-y divide-err/10">
            {critical.map((i) => (
              <IssueRow key={i.id} issue={i} />
            ))}
          </ul>
        </div>
      )}
      {review.summary && <p className="text-[13px] leading-relaxed text-fg-2">{review.summary}</p>}
      <section aria-labelledby="checks-h">
        <h3 id="checks-h" className="eyebrow mb-1">
          Checks · {review.checks.filter((c) => c.passed).length}/{review.checks.length} passed
        </h3>
        <ReviewChecklist review={review} />
      </section>
      {others.length > 0 && (
        <section aria-labelledby="issues-h">
          <h3 id="issues-h" className="eyebrow mb-1">
            Issues · {others.length}
          </h3>
          <ul className="divide-y divide-line-subtle">
            {others.map((i) => (
              <IssueRow key={i.id} issue={i} />
            ))}
          </ul>
        </section>
      )}
      <section aria-labelledby="rev-h">
        <h3 id="rev-h" className="eyebrow mb-2">
          Revisions · {revisions.length}
        </h3>
        {revisions.length ? <RevisionHistory revisions={revisions} /> : <p className="text-[12px] text-fg-3">No revisions were made.</p>}
      </section>
    </div>
  );
}
