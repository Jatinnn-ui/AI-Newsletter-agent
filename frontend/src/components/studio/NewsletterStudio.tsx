import { useState } from "react";
import { Download, ExternalLink, FileCode2, Info, ListOrdered, Monitor, RotateCw, Smartphone } from "lucide-react";
import { useHealth } from "../../hooks/useHealth";
import { api, errorMessage, type FileKind } from "../../lib/api";
import { fmtDateTime } from "../../lib/format";
import type { RunDetail } from "../../lib/types";
import { Button } from "../ui/Button";
import { Meta } from "../ui/Panel";
import { Popover } from "../ui/Popover";
import { Badge } from "../ui/StatusBadge";
import { EmptyState } from "../ui/States";
import { Segmented, TabPanel, Tabs } from "../ui/Tabs";
import { useToast } from "../ui/Toast";
import { cx } from "../ui/cx";
import { MarkdownPreview } from "./MarkdownPreview";
import { CopyButton, NewsletterOutline } from "./NewsletterMetadata";
import { NewsletterPreview } from "./NewsletterPreview";

export function ExportControls({ run }: { run: RunDetail }) {
  const toast = useToast();
  const { health } = useHealth();
  const [busy, setBusy] = useState<FileKind | null>(null);
  const saved = Boolean(run.output);
  // A direct URL can't carry the access token, so "open in a tab" is only offered when auth is off.
  const canOpen = saved && health ? !health.config.auth_required : false;

  async function download(kind: FileKind) {
    setBusy(kind);
    try {
      const name = await api.downloadFile(run.run_id, kind);
      toast({ tone: "success", title: "Download started", description: name });
    } catch (e) {
      toast({ tone: "error", title: `Couldn't download ${kind === "html" ? "HTML" : "Markdown"}`, description: errorMessage(e) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <Button size="sm" icon={Download} onClick={() => download("html")} loading={busy === "html"} disabled={!saved}>
          HTML
        </Button>
        <Button size="sm" icon={Download} onClick={() => download("md")} loading={busy === "md"} disabled={!saved}>
          Markdown
        </Button>
      </div>
      {canOpen ? (
        <a
          href={api.fileUrl(run.run_id, "html")}
          target="_blank"
          rel="noopener noreferrer"
          className="transition-base flex h-8 items-center justify-center gap-1.5 rounded-[8px] border border-line-subtle text-[13px] text-fg-2 hover:border-line hover:bg-elevated hover:text-fg"
        >
          <ExternalLink size={14} aria-hidden /> Open generated file
        </a>
      ) : (
        <p className="text-[12px] leading-snug text-fg-3">
          {saved
            ? "Opening the file in a tab needs an access token this backend requires. Use download instead."
            : "Downloads become available once the newsletter is saved."}
        </p>
      )}
      {run.output && (
        <dl className="mono space-y-1 border-t border-line-subtle pt-2 text-[11px] text-fg-3">
          <div className="truncate" title={run.output.html_filename}>
            <dt className="sr-only">HTML file</dt>
            <dd>{run.output.html_filename}</dd>
          </div>
          <div className="truncate" title={run.output.markdown_filename}>
            <dt className="sr-only">Markdown file</dt>
            <dd>{run.output.markdown_filename}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

/**
 * Compact toolbar above the preview: subject + preheader on the left, review status and
 * secondary metadata/outline/export in popovers on the right. Keeps the iframe full width.
 */
function NewsletterToolbar({ run }: { run: RunDetail }) {
  const draft = run.draft!;
  const review = run.review;
  const saved = Boolean(run.output);
  return (
    <div className="flex flex-wrap items-start gap-x-4 gap-y-2 border-b border-line-subtle px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <h3 className="truncate text-[14px] font-medium text-fg" title={draft.subject}>
            {draft.subject}
          </h3>
          <CopyButton text={draft.subject} label="Copy subject" />
        </div>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[12px] text-fg-3">
          <span className="truncate" title={draft.preheader}>
            {draft.preheader || "No preheader"}
          </span>
          <span aria-hidden>·</span>
          <span className="mono whitespace-nowrap">{draft.sections.length} articles</span>
          <span aria-hidden>·</span>
          <span className="mono whitespace-nowrap">v{draft.version}</span>
        </p>
      </div>

      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        {saved ? <Badge tone="success">Saved</Badge> : <Badge tone="accent">Draft</Badge>}
        {draft.is_test_data && <Badge tone="warning">Fixture</Badge>}
        {review && (
          <Badge tone={review.passed ? "success" : "warning"} title={`Self-review score ${review.score}/100`}>
            <span className="mono">{review.score}</span> {review.passed ? "passed" : "needs work"}
          </Badge>
        )}

        <Popover
          label="Newsletter outline"
          align="end"
          trigger={({ toggle, open, id }) => (
            <Button size="sm" variant="ghost" icon={ListOrdered} aria-expanded={open} aria-controls={id} onClick={toggle}>
              <span className="hidden sm:inline">Outline</span>
            </Button>
          )}
        >
          <div className="max-h-[60vh] overflow-y-auto">
            <h4 className="eyebrow mb-2">Outline · {draft.sections.length} stories</h4>
            <NewsletterOutline draft={draft} />
          </div>
        </Popover>

        <Popover
          label="Generation details"
          align="end"
          trigger={({ toggle, open, id }) => (
            <Button size="sm" variant="ghost" icon={Info} aria-expanded={open} aria-controls={id} onClick={toggle}>
              <span className="hidden sm:inline">Details</span>
            </Button>
          )}
        >
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
        </Popover>

        <Popover
          label="Export newsletter"
          align="end"
          trigger={({ toggle, open, id }) => (
            <Button size="sm" variant="secondary" icon={Download} aria-expanded={open} aria-controls={id} onClick={toggle}>
              Export
            </Button>
          )}
        >
          <h4 className="eyebrow mb-2">Export</h4>
          <ExportControls run={run} />
        </Popover>
      </div>
    </div>
  );
}

export default function NewsletterStudio({ run, onRefresh }: { run: RunDetail; onRefresh: () => void }) {
  const [view, setView] = useState<"preview" | "markdown">("preview");
  const [width, setWidth] = useState<"desktop" | "mobile">("desktop");
  const [reloadKey, setReloadKey] = useState(0);
  const draft = run.draft;

  if (!draft || !run.html) {
    return <EmptyState icon={FileCode2} title="No newsletter yet" description="The preview appears once the agent has written a draft." className="panel py-14" />;
  }

  return (
    <div className="panel flex min-h-0 flex-col overflow-hidden">
      <NewsletterToolbar run={run} />
      <div className="flex flex-wrap items-center gap-2 border-b border-line-subtle px-4 py-2">
        <Tabs
          idPrefix="studio"
          label="Newsletter views"
          value={view}
          onChange={setView}
          items={[
            { id: "preview", label: "Preview" },
            { id: "markdown", label: "Markdown" },
          ]}
        />
        {view === "preview" && (
          <div className="ml-auto flex items-center gap-1">
            <Segmented
              label="Preview width"
              value={width}
              onChange={setWidth}
              options={[
                { value: "desktop", label: <><Monitor size={13} aria-hidden /> <span className="hidden sm:inline">Desktop</span></>, title: "Desktop width" },
                { value: "mobile", label: <><Smartphone size={13} aria-hidden /> <span className="hidden sm:inline">Mobile</span></>, title: "Mobile width (390px)" },
              ]}
            />
            <Button
              size="sm"
              variant="ghost"
              icon={RotateCw}
              onClick={() => {
                onRefresh();
                setReloadKey((k) => k + 1);
              }}
            >
              <span className="sr-only">Refresh preview</span>
            </Button>
          </div>
        )}
      </div>

      <div className={cx("min-h-0 flex-1", view === "markdown" && "p-3 sm:p-4")}>
        <TabPanel idPrefix="studio" id="preview" active={view === "preview"} className="h-full">
          <NewsletterPreview html={run.html} width={width} reloadKey={reloadKey} />
        </TabPanel>
        <TabPanel idPrefix="studio" id="markdown" active={view === "markdown"}>
          {run.markdown ? <MarkdownPreview markdown={run.markdown} /> : <EmptyState icon={FileCode2} title="No Markdown generated" />}
        </TabPanel>
      </div>
    </div>
  );
}
