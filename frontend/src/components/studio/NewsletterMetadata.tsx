import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { fmtDateTime, fmtDay, hostOf, safeHref } from "../../lib/format";
import type { NewsletterDraft, ReviewResult } from "../../lib/types";
import { Badge } from "../ui/StatusBadge";
import { Meta } from "../ui/Panel";
import { useToast } from "../ui/Toast";

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  const toast = useToast();
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          window.setTimeout(() => setDone(false), 1500);
        } catch {
          toast({ tone: "error", title: "Couldn't copy", description: "Clipboard access was blocked by the browser." });
        }
      }}
      aria-label={label}
      title={label}
      className="transition-base inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-fg-3 hover:bg-elevated hover:text-fg"
    >
      {done ? <Check size={13} className="text-ok" aria-hidden /> : <Copy size={13} aria-hidden />}
      <span className="sr-only" aria-live="polite">{done ? "Copied" : ""}</span>
    </button>
  );
}

/** Subject and preheader are read-only: the backend does not accept edits to the saved artifact. */
export function NewsletterMetadata({ draft, review, saved }: { draft: NewsletterDraft; review: ReviewResult | null; saved: boolean }) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-[12px] text-fg-3">Email subject</p>
        <div className="mt-1 flex items-start gap-1.5">
          <p className="min-w-0 flex-1 text-[15px] leading-snug font-medium text-fg">{draft.subject}</p>
          <CopyButton text={draft.subject} label="Copy subject" />
        </div>
      </div>
      <div>
        <p className="text-[12px] text-fg-3">Preheader</p>
        <p className="mt-1 text-[13px] leading-snug text-fg-2">{draft.preheader || "—"}</p>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Meta label="Articles">{draft.sections.length}</Meta>
        <Meta label="Version" mono>
          v{draft.version}
        </Meta>
        <Meta label="Generated">{fmtDateTime(draft.generated_at)}</Meta>
        <Meta label="Review">
          {review ? (
            <span className={review.passed ? "text-ok" : "text-warn"}>
              {review.score}/100 · {review.passed ? "passed" : "needs work"}
            </span>
          ) : (
            "Not reviewed"
          )}
        </Meta>
      </dl>
      <div className="flex flex-wrap gap-1.5">
        {saved ? <Badge tone="success">Saved</Badge> : <Badge tone="accent">Draft</Badge>}
        {draft.is_test_data && <Badge tone="warning">Fixture data</Badge>}
      </div>
    </div>
  );
}

export function NewsletterOutline({ draft }: { draft: NewsletterDraft }) {
  return (
    <ol className="space-y-2.5" aria-label="Newsletter outline">
      {draft.sections.map((s, i) => {
        const href = safeHref(s.source_url);
        return (
          <li key={s.article_id} className="flex gap-2.5">
            <span className="mono mt-0.5 w-4 shrink-0 text-right text-[11px] text-fg-3">{i + 1}</span>
            <div className="min-w-0">
              <p className="text-[13px] leading-snug text-fg">{s.headline}</p>
              <p className="mt-0.5 text-[11px] text-fg-3">
                {s.publisher}
                {s.published_date ? ` · ${fmtDay(s.published_date)}` : " · date unverified"}
                {href && (
                  <>
                    {" · "}
                    <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="mono hover:text-accent">
                      {hostOf(href)}
                    </a>
                  </>
                )}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
