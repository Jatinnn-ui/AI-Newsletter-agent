import { AlertTriangle, CircleSlash, Clock, Send, XCircle } from "lucide-react";
import type { RunDetail } from "../../lib/types";
import { cx } from "../ui/cx";

function Banner({ tone, icon: Icon, title, children, role = "status" }: { tone: "ok" | "warn" | "err" | "muted"; icon: typeof Send; title: string; children?: React.ReactNode; role?: "status" | "alert" }) {
  const cls = {
    ok: "border-ok/25 bg-ok/5 [&_svg]:text-ok",
    warn: "border-warn/25 bg-warn/5 [&_svg]:text-warn",
    err: "border-err/30 bg-err/5 [&_svg]:text-err",
    muted: "border-line bg-surface [&_svg]:text-fg-3",
  }[tone];
  return (
    <div role={role} className={cx("fade-in flex items-start gap-3 rounded-[12px] border px-4 py-3", cls)}>
      <Icon size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-[14px] font-medium text-fg">{title}</p>
        {children && <div className="mt-0.5 text-[13px] text-fg-2">{children}</div>}
      </div>
    </div>
  );
}

export function OutcomeBanner({ run }: { run: RunDetail }) {
  switch (run.status) {
    case "completed":
    case "completed_with_warnings": {
      const warn = run.status === "completed_with_warnings";
      return (
        <Banner tone={warn ? "warn" : "ok"} icon={warn ? AlertTriangle : Send} title="Simulated delivery · Newsletter generated and saved">
          <p>
            “{run.draft?.subject ?? "Newsletter"}” · {run.metrics.article_count} articles
            {run.review ? ` · review ${run.review.score}/100 ${run.review.passed ? "passed" : "did not pass"}` : ""}. Saved to disk only; no email was sent to subscribers.
          </p>
          {warn && run.warnings.length > 0 && (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[12px] text-fg-2">
              {run.warnings.slice(0, 4).map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </Banner>
      );
    }
    case "failed":
      return (
        <Banner tone="err" icon={XCircle} title="Run failed" role="alert">
          <p className="break-words">{run.error ?? "The agent stopped with an error. See the activity log for details."}</p>
        </Banner>
      );
    case "cancelled":
      return <Banner tone="muted" icon={CircleSlash} title="Run cancelled">Nothing was saved for this run.</Banner>;
    case "expired":
      return (
        <Banner tone="muted" icon={Clock} title="Approval window expired">
          This run waited too long for a decision and was closed. Start a new run to continue.
        </Banner>
      );
    default:
      return null;
  }
}
