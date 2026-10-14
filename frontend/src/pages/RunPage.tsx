import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Activity, ChevronRight, FileText, ListChecks, Newspaper, SearchX } from "lucide-react";
import { ActivityFeed } from "../components/run/ActivityFeed";
import { DraftApprovalPanel, ResearchApprovalPanel } from "../components/run/ApprovalPanel";
import { ArticleSelectionList } from "../components/run/ArticleSelectionList";
import { OutcomeBanner } from "../components/run/OutcomeBanner";
import { PlanSummary } from "../components/run/PlanSummary";
import { ReviewPanel, ReviewScore } from "../components/run/ReviewPanel";
import { RunHeader } from "../components/run/RunHeader";
import { WorkflowStrip } from "../components/run/WorkflowTimeline";
import { PageContainer } from "../components/shell/AppShell";
import { Button } from "../components/ui/Button";
import { ConfirmDialog } from "../components/ui/Dialog";
import { Panel } from "../components/ui/Panel";
import { Badge } from "../components/ui/StatusBadge";
import { cx } from "../components/ui/cx";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { TabPanel, Tabs } from "../components/ui/Tabs";
import { useToast } from "../components/ui/Toast";
import { useRunStream } from "../hooks/useRunStream";
import { api, ApiError, errorMessage } from "../lib/api";
import { statusLabel } from "../lib/format";
import { Link, paths, useRouter } from "../lib/router";
import { isTerminal, type RunDetail, type RunStatus } from "../lib/types";

const NewsletterStudio = lazy(() => import("../components/studio/NewsletterStudio"));

// The left workspace shows one primary surface at a time. The newsletter leads whenever a
// draft exists; research/plan stay reachable without pushing the preview aside.
type WorkTab = "newsletter" | "research" | "plan";

function defaultWorkTab(run: RunDetail): WorkTab {
  if (run.status === "awaiting_research_approval") return "research";
  if (run.draft) return "newsletter";
  if (run.candidates.length) return "research";
  return "plan";
}

/** Local article selection for the research approval gate; reset when a new approval is requested. */
function useSelection(run: RunDetail | null) {
  const key = run?.approval?.kind === "research" ? `${run.run_id}:${run.approval.requested_at}` : null;
  const [state, setState] = useState<{ key: string | null; ids: string[] }>({ key: null, ids: [] });
  if (key && state.key !== key && run) setState({ key, ids: run.proposed_ids });
  return [state.ids, (ids: string[]) => setState((s) => ({ ...s, ids }))] as const;
}

export function RunPage({ runId, initialTab }: { runId: string; initialTab: string | null }) {
  const { run, error, stream, refresh, apply } = useRunStream(runId);
  const { navigate } = useRouter();
  const toast = useToast();
  const [tab, setTab] = useState<WorkTab | null>((["newsletter", "research", "plan"] as const).includes(initialTab as WorkTab) ? (initialTab as WorkTab) : null);
  // On narrow screens the right rail (review + activity) becomes a tab alongside the workspace.
  const [mobilePane, setMobilePane] = useState<"work" | "insights">("work");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [selection, setSelection] = useSelection(run);
  const [announce, setAnnounce] = useState("");
  const lastStatus = useRef<RunStatus | null>(null);

  // Follow the run to the relevant surface when its status changes (not on every refresh).
  useEffect(() => {
    if (!run || run.status === lastStatus.current) return;
    const first = lastStatus.current === null;
    lastStatus.current = run.status;
    if (!first || !tab) setTab(defaultWorkTab(run));
    if (!first) {
      setAnnounce(`Run status: ${statusLabel[run.status]}`);
      if (run.status === "awaiting_research_approval") setMobilePane("work");
    }
  }, [run, tab]);

  const changeTab = (t: WorkTab) => {
    setTab(t);
    navigate(paths.run(runId, t), { replace: true });
  };

  async function cancel() {
    setCancelling(true);
    try {
      const r = await api.cancel(runId);
      apply(r);
      toast({
        tone: "info",
        title: r.status === "cancelled" ? "Run cancelled" : "Cancellation requested",
        description: r.status === "cancelled" ? undefined : "The agent stops at the next safe point.",
      });
      setConfirmCancel(false);
    } catch (e) {
      toast({ tone: "error", title: "Couldn't cancel", description: errorMessage(e) });
      void refresh();
    } finally {
      setCancelling(false);
    }
  }

  if (!run) {
    return (
      <PageContainer wide>
        {error ? (
          error instanceof ApiError && error.status === 404 ? (
            <EmptyState
              icon={SearchX}
              title="Run not found"
              description="It may have been removed by the retention policy, or the link is wrong."
              action={
                <Link to={paths.history} className="text-[13px] text-accent hover:underline">
                  Back to run history
                </Link>
              }
              className="panel py-16"
            />
          ) : (
            <ErrorState title="Couldn't load this run" message={error.message} onRetry={refresh} />
          )
        ) : (
          <LoadingState label="Loading run…" />
        )}
      </PageContainer>
    );
  }

  const terminal = isTerminal(run.status);
  const active = !terminal;
  const awaitingResearch = run.status === "awaiting_research_approval";
  const awaitingDraft = run.status === "awaiting_draft_approval";
  const current = tab ?? defaultWorkTab(run);
  const requested = run.plan?.config.article_count ?? run.request.article_count ?? null;
  const shownSelection = awaitingResearch ? selection : run.selected_ids.length ? run.selected_ids : run.proposed_ids;
  const critical = run.review?.issues.filter((i) => i.severity === "critical").length ?? 0;
  const hasInsights = Boolean(run.review) || run.tool_calls.length > 0 || run.logs.length > 0;

  const workTabs = [
    { id: "newsletter" as const, label: <span className="inline-flex items-center gap-1.5"><Newspaper size={13} aria-hidden /> Newsletter</span>, badge: run.draft ? <span className="mono text-[11px] text-fg-3">v{run.draft.version}</span> : undefined },
    { id: "research" as const, label: <span className="inline-flex items-center gap-1.5"><FileText size={13} aria-hidden /> Research</span>, badge: run.candidates.length ? <span className="mono text-[11px] text-fg-3">{run.candidates.length}</span> : undefined },
    { id: "plan" as const, label: <span className="inline-flex items-center gap-1.5"><ListChecks size={13} aria-hidden /> Plan</span> },
  ];

  const workspace = (
    <div className="min-w-0 space-y-3">
      {/* Only show the workspace switcher when there is more than one meaningful surface. */}
      {(run.draft || run.candidates.length > 0 || run.plan) && (
        <Tabs idPrefix="work" label="Workspace views" items={workTabs} value={current} onChange={changeTab} />
      )}

      <TabPanel idPrefix="work" id="newsletter" active={current === "newsletter"} className="h-full">
        {run.draft ? (
          <Suspense fallback={<LoadingState label="Loading preview…" />}>
            <NewsletterStudio run={run} onRefresh={refresh} />
          </Suspense>
        ) : (
          <Panel className="py-14">
            <EmptyState
              icon={Newspaper}
              title={active ? "Newsletter not written yet" : "No newsletter produced"}
              description={active ? "The preview opens here as soon as the agent finishes a draft." : "This run ended before a draft was written."}
            />
          </Panel>
        )}
      </TabPanel>

      <TabPanel idPrefix="work" id="research" active={current === "research"}>
        <Panel>
          <ArticleSelectionList
            articles={run.candidates}
            selected={shownSelection}
            editable={awaitingResearch}
            onChange={setSelection}
            requested={requested}
            emptyHint={active ? "Research is in progress. Candidates appear when the search completes." : "This run produced no candidate articles."}
          />
        </Panel>
      </TabPanel>

      <TabPanel idPrefix="work" id="plan" active={current === "plan"}>
        <Panel>
          <PlanSummary plan={run.plan} active={active} />
        </Panel>
      </TabPanel>
    </div>
  );

  const insights = <InsightsRail run={run} active={active} />;

  return (
    <PageContainer wide>
      <p className="sr-only" role="status" aria-live="polite">
        {announce}
      </p>

      <RunHeader run={run} stream={stream} onCancel={() => setConfirmCancel(true)} />
      <div className="mb-4">
        <WorkflowStrip run={run} />
      </div>

      {error && <ErrorState className="mb-4" title="Live updates interrupted" message={`${error.message} Showing the last known state.`} onRetry={refresh} />}

      {/* Actionable moments span the full width above the split. */}
      <div className="space-y-3">
        {awaitingResearch && <ResearchApprovalPanel run={run} selected={selection} onApplied={apply} onCancel={() => setConfirmCancel(true)} />}
        {awaitingDraft && <DraftApprovalPanel run={run} onApplied={apply} onCancel={() => setConfirmCancel(true)} />}
        <OutcomeBanner run={run} />
        {critical > 0 && !awaitingDraft && terminal && (
          <ErrorState title="Critical review findings" message={`The final review reported ${critical} critical ${critical === 1 ? "issue" : "issues"}. Review them before using this newsletter.`} />
        )}
      </div>

      {/* Mobile / tablet: workspace and insights as tabs so the preview never shrinks. */}
      {hasInsights && (
        <div className="mt-4 xl:hidden">
          <Tabs
            idPrefix="pane"
            label="Run panes"
            value={mobilePane}
            onChange={setMobilePane}
            items={[
              { id: "work", label: "Workspace" },
              { id: "insights", label: "Review & activity" },
            ]}
          />
        </div>
      )}

      <div className="mt-4 grid gap-5 xl:grid-cols-[minmax(0,7fr)_minmax(300px,3fr)]">
        <div className={cx("min-w-0", mobilePane === "work" ? "block" : "hidden xl:block")}>{workspace}</div>
        <div className={cx("min-w-0", mobilePane === "insights" ? "block" : "hidden xl:block")}>
          {hasInsights ? insights : <div className="hidden xl:block" aria-hidden />}
        </div>
      </div>

      {terminal && (
        <div className="mt-5 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => navigate(paths.overview)}>
            Start a new run
          </Button>
        </div>
      )}

      <ConfirmDialog
        open={confirmCancel}
        title="Cancel this run?"
        description={
          run.status === "running"
            ? "The agent stops at the next safe point. Partial work is discarded and nothing is saved."
            : "The run will be closed and nothing will be saved."
        }
        confirmLabel="Cancel run"
        destructive
        loading={cancelling}
        onConfirm={cancel}
        onClose={() => setConfirmCancel(false)}
      />
    </PageContainer>
  );
}

/**
 * Narrow right column: self-review summary with a link to the full review, plus the agent
 * activity in a collapsible drawer that is closed by default (raw tool output stays hidden).
 */
function InsightsRail({ run, active }: { run: RunDetail; active: boolean }) {
  const [reviewOpen, setReviewOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const errors = run.tool_calls.filter((c) => c.status === "error").length;

  return (
    <aside aria-label="Review and activity" className="space-y-4 xl:sticky xl:top-6 xl:self-start">
      {run.review ? (
        <Panel className="p-4">
          <div className="mb-3 flex items-center gap-2">
            <h2 className="text-[13px] font-medium text-fg">Self-review</h2>
            {run.revisions.length > 0 && (
              <Badge>
                {run.revisions.length} revision{run.revisions.length > 1 ? "s" : ""}
              </Badge>
            )}
          </div>
          <ReviewScore review={run.review} />

          <button
            type="button"
            aria-expanded={reviewOpen}
            onClick={() => setReviewOpen((o) => !o)}
            className="transition-base mt-4 flex w-full items-center gap-1.5 border-t border-line-subtle pt-3 text-[12px] text-fg-3 hover:text-fg"
          >
            <ChevronRight size={13} className={reviewOpen ? "rotate-90 transition-base" : "transition-base"} aria-hidden />
            {reviewOpen ? "Hide" : "Show"} checks, issues and revisions
          </button>
          {reviewOpen && (
            <div className="fade-in mt-3">
              <ReviewPanel review={run.review} revisions={run.revisions} pending={active} />
            </div>
          )}
        </Panel>
      ) : (
        active && (
          <Panel className="p-4">
            <h2 className="mb-2 text-[13px] font-medium text-fg">Self-review</h2>
            <p className="text-[12px] text-fg-3">The self-review runs after the newsletter draft is written. Its score and findings will appear here.</p>
          </Panel>
        )
      )}

      <Panel>
        <button
          type="button"
          aria-expanded={activityOpen}
          aria-controls="activity-drawer"
          onClick={() => setActivityOpen((o) => !o)}
          className="transition-base flex w-full items-center gap-2 px-4 py-3 text-left hover:bg-elevated/40"
        >
          <Activity size={14} strokeWidth={1.75} className="text-fg-3" aria-hidden />
          <span className="text-[13px] font-medium text-fg">Agent activity</span>
          <span className="mono text-[11px] text-fg-3">
            {run.tool_calls.length} calls{errors ? ` · ${errors} failed` : ""}
          </span>
          <ChevronRight size={14} className={activityOpen ? "ml-auto rotate-90 text-fg-3 transition-base" : "ml-auto text-fg-3 transition-base"} aria-hidden />
        </button>
        {activityOpen && (
          <div id="activity-drawer" className="fade-in max-h-[60vh] overflow-y-auto border-t border-line-subtle">
            <ActivityFeed calls={run.tool_calls} logs={run.logs} active={active} />
          </div>
        )}
      </Panel>
    </aside>
  );
}
