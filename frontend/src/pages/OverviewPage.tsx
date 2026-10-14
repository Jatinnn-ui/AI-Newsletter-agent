import { History, Mail, ServerCrash } from "lucide-react";
import { GoalComposer, StartBackendHint } from "../components/composer/GoalComposer";
import { NewsletterList } from "../components/history/NewsletterList";
import { RunHistoryTable } from "../components/history/RunHistoryTable";
import { PageContainer, PageHeader } from "../components/shell/AppShell";
import { ConnectionStatus } from "../components/shell/ConnectionStatus";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { EmptyState, ErrorState, SkeletonRows } from "../components/ui/States";
import { useHealth } from "../hooks/useHealth";
import { useNewsletters, useRuns } from "../hooks/useRuns";
import { API_BASE } from "../lib/api";
import { Link, paths } from "../lib/router";

function ViewAll({ to }: { to: string }) {
  return (
    <Link to={to} className="text-[12px] text-fg-3 hover:text-accent">
      View all
    </Link>
  );
}

export function OverviewPage() {
  const { connection, error, recheck } = useHealth();
  const offline = connection === "offline";
  const runs = useRuns(6);
  const newsletters = useNewsletters(30, 5);

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Workspace / Overview"
        title="Newsletter Workspace"
        description="Turn a goal into a researched, reviewed newsletter."
        actions={<ConnectionStatus />}
      />

      {offline && (
        <ErrorState className="mb-5" title={`Can't reach the backend at ${API_BASE || "this origin"}`} message={error ?? "Connection failed."} onRetry={recheck}>
          <StartBackendHint />
        </ErrorState>
      )}

      <GoalComposer />

      <div className="mt-6 grid min-w-0 gap-5 lg:grid-cols-2">
        <Panel aria-labelledby="recent-runs" className="min-w-0">
          <PanelHeader id="recent-runs" title="Recent runs" actions={<ViewAll to={paths.history} />} />
          {runs.error && !runs.runs ? (
            <EmptyState icon={ServerCrash} title="Run history unavailable" description={runs.error} />
          ) : !runs.runs ? (
            <SkeletonRows rows={4} />
          ) : runs.runs.length ? (
            <RunHistoryTable runs={runs.runs} compact />
          ) : (
            <EmptyState icon={History} title="No runs yet" description="Runs you start appear here with their live status." />
          )}
        </Panel>

        <Panel aria-labelledby="recent-newsletters" className="min-w-0">
          <PanelHeader id="recent-newsletters" title="Recent newsletters" actions={<ViewAll to={paths.newsletters} />} />
          {newsletters.error && !newsletters.items ? (
            <EmptyState icon={ServerCrash} title="Newsletters unavailable" description={newsletters.error} />
          ) : !newsletters.items ? (
            <SkeletonRows rows={4} />
          ) : newsletters.items.length ? (
            <NewsletterList items={newsletters.items} />
          ) : (
            <EmptyState icon={Mail} title="No newsletters saved yet" description="Completed runs save an HTML and Markdown newsletter you can preview and download." />
          )}
        </Panel>
      </div>
    </PageContainer>
  );
}
