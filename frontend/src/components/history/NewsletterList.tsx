import { ArrowUpRight, FlaskConical } from "lucide-react";
import { fmtDateTime } from "../../lib/format";
import { Link, paths } from "../../lib/router";
import type { RunDetail } from "../../lib/types";
import { Badge } from "../ui/StatusBadge";

export function NewsletterList({ items }: { items: RunDetail[] }) {
  return (
    <ul aria-label="Newsletters">
      {items.map((r) => {
        const review = r.review;
        return (
          <li key={r.run_id} className="border-b border-line-subtle last:border-b-0">
            <Link to={paths.run(r.run_id, "newsletter")} className="transition-base group flex items-center gap-3 px-4 py-3 hover:bg-elevated/50">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] text-fg">{r.draft?.subject ?? "Untitled newsletter"}</p>
                <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-fg-3">
                  <span>{fmtDateTime(r.output?.saved_at ?? r.updated_at)}</span>
                  <span className="mono">· {r.metrics.article_count} articles</span>
                  {r.deterministic && (
                    <span className="inline-flex items-center gap-1 text-warn/80">
                      · <FlaskConical size={10} aria-hidden /> demo
                    </span>
                  )}
                </p>
              </div>
              {review ? (
                <Badge tone={review.passed ? "success" : "warning"} title={`Self-review score ${review.score}/100`}>
                  <span className="mono">{review.score}</span> {review.passed ? "passed" : "needs work"}
                </Badge>
              ) : (
                <Badge>Not reviewed</Badge>
              )}
              <span className="transition-base inline-flex items-center gap-1 text-[12px] text-fg-3 group-hover:text-accent">
                <span className="hidden sm:inline">Open</span>
                <ArrowUpRight size={14} aria-hidden />
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
