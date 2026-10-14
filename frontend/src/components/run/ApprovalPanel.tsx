import { useState } from "react";
import { Check, Hand, RefreshCcw, X } from "lucide-react";
import { api, errorMessage } from "../../lib/api";
import type { RunDetail } from "../../lib/types";
import { Button } from "../ui/Button";
import { ErrorState } from "../ui/States";
import { MAX_SELECTED } from "./ArticleSelectionList";

function Shell({ title, children, actions }: { title: string; children: React.ReactNode; actions: React.ReactNode }) {
  return (
    <section aria-labelledby="approval-title" className="fade-in rounded-[12px] border border-accent/40 bg-accent-soft/60">
      <div className="flex flex-wrap items-start gap-3 px-4 py-3.5">
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
          <Hand size={13} strokeWidth={2} aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id="approval-title" className="text-[14px] font-medium text-fg">
            {title}
          </h2>
          <div className="mt-0.5 text-[13px] text-fg-2">{children}</div>
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">{actions}</div>
      </div>
    </section>
  );
}

export function ResearchApprovalPanel({
  run,
  selected,
  onApplied,
  onCancel,
}: {
  run: RunDetail;
  selected: string[];
  onApplied: (r: RunDetail) => void;
  onCancel: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = selected.length >= 1 && selected.length <= MAX_SELECTED;
  const unchanged = selected.length === run.proposed_ids.length && selected.every((id) => run.proposed_ids.includes(id));

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      onApplied(await api.approveResearch(run.run_id, selected));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <Shell
        title="Waiting for your approval"
        actions={
          <>
            <Button size="sm" variant="ghost" icon={X} onClick={onCancel} disabled={busy}>
              Cancel run
            </Button>
            <Button size="sm" variant="primary" icon={Check} onClick={approve} loading={busy} disabled={!valid}>
              Approve research
            </Button>
          </>
        }
      >
        Review the {run.candidates.length} candidate articles below. The agent picked {run.proposed_ids.length}; you have{" "}
        <span className="mono text-fg">{selected.length}</span> selected{unchanged ? "" : " (edited)"}. It will summarize and write once you confirm.
        {!valid && <span className="mt-1 block text-warn">Select between 1 and {MAX_SELECTED} articles.</span>}
      </Shell>
      {error && <ErrorState title="Approval failed" message={error} />}
    </div>
  );
}

export function DraftApprovalPanel({ run, onApplied, onCancel }: { run: RunDetail; onApplied: (r: RunDetail) => void; onCancel: () => void }) {
  const [busy, setBusy] = useState<"approve" | "revise" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const used = run.approval?.user_revisions_used ?? 0;
  const max = run.approval?.user_revisions_max ?? 0;
  const canRevise = used < max;
  const critical = run.review?.issues.filter((i) => i.severity === "critical").length ?? 0;

  async function act(kind: "approve" | "revise") {
    setBusy(kind);
    setError(null);
    try {
      onApplied(kind === "approve" ? await api.approveNewsletter(run.run_id) : await api.revise(run.run_id, feedback));
      if (kind === "revise") setFeedback("");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2">
      <Shell
        title="Waiting for your approval"
        actions={
          <>
            <Button size="sm" variant="ghost" icon={X} onClick={onCancel} disabled={busy !== null}>
              Cancel run
            </Button>
            <Button size="sm" variant="primary" icon={Check} onClick={() => act("approve")} loading={busy === "approve"} disabled={busy !== null}>
              Approve and save
            </Button>
          </>
        }
      >
        Draft v{run.draft?.version ?? 1} is ready
        {run.review ? ` and scored ${run.review.score}/100 in self-review` : ""}. Nothing is saved until you approve.
        {critical > 0 && <span className="mt-1 block text-err">The reviewer flagged {critical} critical {critical === 1 ? "issue" : "issues"}. Consider requesting a revision.</span>}
      </Shell>
      <div className="panel p-3">
        <label htmlFor="revision-feedback" className="mb-1.5 block text-[12px] font-medium text-fg-2">
          Request a revision <span className="font-normal text-fg-3">· {used}/{max} used</span>
        </label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <textarea
            id="revision-feedback"
            rows={2}
            maxLength={1000}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            disabled={!canRevise || busy !== null}
            placeholder={canRevise ? "e.g. Make the summaries shorter and lead with the funding news." : "Revision limit reached. Approve or cancel this run."}
            className="field min-h-[60px] flex-1 resize-y text-[13px]"
          />
          <Button icon={RefreshCcw} onClick={() => act("revise")} loading={busy === "revise"} disabled={!canRevise || busy !== null} className="sm:self-end">
            Revise newsletter
          </Button>
        </div>
        <p className="mt-1.5 text-[12px] text-fg-3">The agent revises the draft, runs self-review again and pauses here for approval.</p>
      </div>
      {error && <ErrorState title="Action failed" message={error} />}
    </div>
  );
}
