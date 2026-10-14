import { Mail, RotateCw, ServerCrash } from "lucide-react";
import { NewsletterList } from "../components/history/NewsletterList";
import { PageContainer, PageHeader } from "../components/shell/AppShell";
import { Button } from "../components/ui/Button";
import { Panel } from "../components/ui/Panel";
import { EmptyState, SkeletonRows } from "../components/ui/States";
import { useNewsletters } from "../hooks/useRuns";
import { paths, useRouter } from "../lib/router";

export function NewslettersPage() {
  const { items, error, loading, reload } = useNewsletters(100, 50);
  const { navigate } = useRouter();
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Workspace / Newsletters"
        title="Newsletters"
        description="Saved newsletters from completed runs. Delivery is simulated: files are saved, never emailed."
        actions={
          <Button size="sm" variant="ghost" icon={RotateCw} onClick={reload} loading={loading && Boolean(items)}>
            Refresh
          </Button>
        }
      />
      <Panel>
        {error && !items ? (
          <EmptyState icon={ServerCrash} title="Couldn't load newsletters" description={error} action={<Button size="sm" onClick={reload}>Try again</Button>} />
        ) : !items ? (
          <SkeletonRows rows={5} />
        ) : items.length ? (
          <>
            <NewsletterList items={items} />
            {error && <p className="border-t border-line-subtle px-4 py-2.5 text-[12px] text-warn">{error}</p>}
          </>
        ) : (
          <EmptyState
            icon={Mail}
            title="No newsletters saved yet"
            description="When a run completes, its HTML and Markdown newsletter appears here."
            action={
              <Button size="sm" variant="primary" onClick={() => navigate(paths.overview)}>
                New run
              </Button>
            }
          />
        )}
      </Panel>
    </PageContainer>
  );
}
