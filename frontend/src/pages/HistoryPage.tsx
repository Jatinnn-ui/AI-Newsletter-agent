import { useMemo, useState } from "react";
import { History, RotateCw, Search, ServerCrash } from "lucide-react";
import { RunHistoryTable } from "../components/history/RunHistoryTable";
import { PageContainer, PageHeader } from "../components/shell/AppShell";
import { Button } from "../components/ui/Button";
import { Panel } from "../components/ui/Panel";
import { Select } from "../components/ui/Select";
import { EmptyState, ErrorState, SkeletonRows } from "../components/ui/States";
import { useNewsletters, useRuns } from "../hooks/useRuns";
import { paths, useRouter } from "../lib/router";
import type { ExecutionMode, RunStatus, RunSummary } from "../lib/types";

type StatusFilter = "all" | "active" | "approval" | "completed" | "failed" | "closed";
const STATUS_GROUPS: Record<Exclude<StatusFilter, "all">, RunStatus[]> = {
  active: ["queued", "running"],
  approval: ["awaiting_research_approval", "awaiting_draft_approval"],
  completed: ["completed", "completed_with_warnings"],
  failed: ["failed"],
  closed: ["cancelled", "expired"],
};
const STATUS_LABELS: Record<StatusFilter, string> = {
  all: "All statuses",
  active: "Running or queued",
  approval: "Needs approval",
  completed: "Completed",
  failed: "Failed",
  closed: "Cancelled or expired",
};

const LIMIT = 100;

function FilterSelect<T extends string>({ id, label, value, onChange, options }: { id: string; label: string; value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return (
    <div className="w-full sm:w-auto">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value as T)} className="sm:w-auto">
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </Select>
    </div>
  );
}

export function HistoryPage() {
  const { runs, error, loading, reload } = useRuns(LIMIT);
  // Subjects only exist on run details; completed-run details are loaded (and cached) for search.
  const newsletters = useNewsletters(LIMIT, 40);
  const { navigate } = useRouter();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [mode, setMode] = useState<"all" | ExecutionMode>("all");
  const [sort, setSort] = useState<"latest" | "oldest">("latest");

  const subjects = useMemo(() => {
    const m: Record<string, string> = {};
    for (const n of newsletters.items ?? []) if (n.draft?.subject) m[n.run_id] = n.draft.subject;
    return m;
  }, [newsletters.items]);

  const filtered = useMemo(() => {
    if (!runs) return null;
    const q = query.trim().toLowerCase();
    const out = runs.filter((r: RunSummary) => {
      if (status !== "all" && !STATUS_GROUPS[status].includes(r.status)) return false;
      if (mode !== "all" && r.mode !== mode) return false;
      if (q && !r.goal.toLowerCase().includes(q) && !(subjects[r.run_id] ?? "").toLowerCase().includes(q) && !r.run_id.startsWith(q)) return false;
      return true;
    });
    out.sort((a, b) => (sort === "latest" ? b.created_at.localeCompare(a.created_at) : a.created_at.localeCompare(b.created_at)));
    return out;
  }, [runs, query, status, mode, sort, subjects]);

  const filtersActive = Boolean(query.trim()) || status !== "all" || mode !== "all";

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Workspace / Run history"
        title="Run History"
        description="Every run the backend has recorded, with its real status."
        actions={
          <Button size="sm" variant="ghost" icon={RotateCw} onClick={reload} loading={loading && Boolean(runs)}>
            Refresh
          </Button>
        }
      />

      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="relative min-w-0 flex-1 sm:min-w-[240px]">
          <Search size={14} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-fg-3" aria-hidden />
          <label htmlFor="history-search" className="sr-only">
            Search by goal or subject
          </label>
          <input id="history-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search goal or subject" className="field h-9 pl-9 text-[13px]" />
        </div>
        <FilterSelect id="f-status" label="Filter by status" value={status} onChange={setStatus} options={Object.entries(STATUS_LABELS) as [StatusFilter, string][]} />
        <FilterSelect
          id="f-mode"
          label="Filter by mode"
          value={mode}
          onChange={setMode}
          options={[
            ["all", "All modes"],
            ["autonomous", "Autonomous"],
            ["human_in_the_loop", "Human-in-the-loop"],
          ]}
        />
        <FilterSelect
          id="f-sort"
          label="Sort"
          value={sort}
          onChange={setSort}
          options={[
            ["latest", "Latest first"],
            ["oldest", "Oldest first"],
          ]}
        />
      </div>

      {error && runs && <ErrorState className="mb-4" title="Refresh failed" message={error} onRetry={reload} />}

      <Panel>
        {error && !runs ? (
          <EmptyState icon={ServerCrash} title="Couldn't load run history" description={error} action={<Button size="sm" onClick={reload}>Try again</Button>} />
        ) : !filtered ? (
          <SkeletonRows rows={6} />
        ) : filtered.length ? (
          <>
            <RunHistoryTable runs={filtered} subjects={subjects} />
            <p className="border-t border-line-subtle px-4 py-2.5 text-[12px] text-fg-3" aria-live="polite">
              Showing {filtered.length} of {runs!.length} runs{runs!.length >= LIMIT ? ` (latest ${LIMIT} loaded)` : ""}.
            </p>
          </>
        ) : filtersActive ? (
          <EmptyState
            icon={Search}
            title="No runs match these filters"
            action={
              <Button
                size="sm"
                onClick={() => {
                  setQuery("");
                  setStatus("all");
                  setMode("all");
                }}
              >
                Clear filters
              </Button>
            }
          />
        ) : (
          <EmptyState icon={History} title="No runs yet" description="Start a run from the overview to see it here." action={<Button size="sm" variant="primary" onClick={() => navigate(paths.overview)}>New run</Button>} />
        )}
      </Panel>
    </PageContainer>
  );
}
