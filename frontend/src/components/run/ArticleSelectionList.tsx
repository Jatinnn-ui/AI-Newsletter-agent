import { memo } from "react";
import { CalendarDays, ExternalLink, FileText, Info, Newspaper, X } from "lucide-react";
import { fmtDay, hostOf, safeHref, truncate } from "../../lib/format";
import type { Article } from "../../lib/types";
import { Button } from "../ui/Button";
import { Badge } from "../ui/StatusBadge";
import { cx } from "../ui/cx";
import { EmptyState } from "../ui/States";

export const MAX_SELECTED = 7;

export const ArticleCard = memo(function ArticleCard({
  article,
  rank,
  selected,
  editable,
  onToggle,
  disableSelect,
}: {
  article: Article;
  rank: number;
  selected: boolean;
  editable: boolean;
  onToggle?: (id: string) => void;
  disableSelect?: boolean;
}) {
  const href = safeHref(article.url);
  const date = fmtDay(article.published_date);
  const inputId = `article-${article.id}`;
  return (
    <li
      className={cx(
        "transition-base group relative flex gap-3 border-b border-line-subtle px-4 py-3.5 last:border-b-0",
        selected ? "bg-transparent" : "bg-transparent opacity-70 hover:opacity-100",
      )}
    >
      <div className="flex w-5 shrink-0 flex-col items-center gap-2 pt-0.5">
        {editable ? (
          <input
            id={inputId}
            type="checkbox"
            checked={selected}
            disabled={!selected && disableSelect}
            onChange={() => onToggle?.(article.id)}
            className="h-4 w-4 cursor-pointer accent-[var(--accent-primary)] disabled:cursor-not-allowed"
            aria-describedby={`${inputId}-meta`}
          />
        ) : (
          <span
            aria-hidden
            className={cx("mono flex h-5 w-5 items-center justify-center rounded text-[10px]", selected ? "bg-accent-soft text-accent" : "bg-elevated text-fg-3")}
          >
            {rank}
          </span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-2">
          {editable ? (
            <label htmlFor={inputId} className="min-w-0 flex-1 cursor-pointer text-[14px] leading-snug font-medium text-fg">
              {article.title}
            </label>
          ) : (
            <h3 className="min-w-0 flex-1 text-[14px] leading-snug font-medium text-fg">{article.title}</h3>
          )}
          {!editable && <span className="sr-only">{selected ? "Included" : "Not selected"}</span>}
        </div>
        <div id={`${inputId}-meta`} className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-fg-3">
          <span className="inline-flex items-center gap-1 text-fg-2">
            <Newspaper size={12} strokeWidth={1.75} aria-hidden />
            {article.publisher || hostOf(article.url)}
          </span>
          {date ? (
            <span className="inline-flex items-center gap-1" title={article.date_source === "page_metadata" ? "Date from page metadata" : "Date from search API"}>
              <CalendarDays size={12} strokeWidth={1.75} aria-hidden />
              {date}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-warn/90" title={article.date_note ?? undefined}>
              <CalendarDays size={12} strokeWidth={1.75} aria-hidden />
              Date unverified
            </span>
          )}
          <span className="inline-flex items-center gap-1" title={article.retrieval_note ?? undefined}>
            <FileText size={12} strokeWidth={1.75} aria-hidden />
            {article.content_basis === "full_text" ? "Full text" : "Snippet only"}
          </span>
          <span className="mono" title={article.rank_reasons.join("\n") || undefined}>
            score {article.final_score.toFixed(2)}
          </span>
          {article.duplicates_merged.length > 0 && <span>+{article.duplicates_merged.length} duplicate merged</span>}
          {article.is_test_data && <Badge tone="warning">Fixture</Badge>}
        </div>
        {article.snippet && <p className="mt-1.5 text-[13px] leading-relaxed text-fg-2">{truncate(article.snippet, 260)}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-1">
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="transition-base mono inline-flex h-6 max-w-full items-center gap-1 rounded px-1.5 -ml-1.5 text-[11px] text-fg-3 hover:bg-elevated hover:text-accent"
            >
              <span className="truncate">{hostOf(href)}</span>
              <ExternalLink size={11} aria-hidden />
              <span className="sr-only">(opens source in a new tab)</span>
            </a>
          ) : (
            <span className="mono text-[11px] text-fg-3">source link unavailable</span>
          )}
          {editable && selected && (
            <Button size="sm" variant="ghost" icon={X} onClick={() => onToggle?.(article.id)} className="ml-auto h-6 px-2 text-[12px]" aria-label={`Remove “${truncate(article.title, 60)}” from selection`}>
              Remove
            </Button>
          )}
        </div>
      </div>
    </li>
  );
});

export function ArticleSelectionList({
  articles,
  selected,
  editable,
  onChange,
  requested,
  emptyHint,
}: {
  articles: Article[];
  selected: string[];
  editable: boolean;
  onChange?: (ids: string[]) => void;
  requested?: number | null;
  emptyHint?: string;
}) {
  const sel = new Set(selected);
  // Keep the agent's ranking order; selected first when read-only.
  const ordered = editable ? articles : [...articles].sort((a, b) => Number(sel.has(b.id)) - Number(sel.has(a.id)));
  const toggle = (id: string) => {
    if (!onChange) return;
    onChange(sel.has(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  };
  const atMax = selected.length >= MAX_SELECTED;
  const short = requested != null && articles.length > 0 && articles.length < requested;

  if (!articles.length) {
    return <EmptyState icon={Newspaper} title="No articles yet" description={emptyHint ?? "Candidate articles appear here once research completes."} />;
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 border-b border-line-subtle px-4 py-2.5">
        <p className="text-[12px] text-fg-2" aria-live="polite">
          <span className="mono text-fg">{selected.length}</span> of {articles.length} selected
          {editable && atMax && <span className="text-fg-3"> · maximum {MAX_SELECTED}</span>}
        </p>
        {editable && (
          <div className="ml-auto flex gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onChange?.(articles.slice(0, MAX_SELECTED).map((a) => a.id))}
              disabled={selected.length === Math.min(articles.length, MAX_SELECTED)}
              title={articles.length > MAX_SELECTED ? `Selects the top ${MAX_SELECTED} ranked articles` : undefined}
            >
              Select all
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onChange?.([])} disabled={!selected.length}>
              Deselect all
            </Button>
          </div>
        )}
      </div>
      {short && (
        <div className="flex items-start gap-2 border-b border-line-subtle bg-warn/5 px-4 py-2.5 text-[12px] text-fg-2">
          <Info size={13} className="mt-0.5 shrink-0 text-warn" aria-hidden />
          <p>
            Research found {articles.length} usable {articles.length === 1 ? "article" : "articles"} against the {requested} requested. The agent does not invent stories to fill the gap; widen the lookback period or broaden the goal for more coverage.
          </p>
        </div>
      )}
      <ul aria-label="Candidate articles">
        {ordered.map((a, i) => (
          <ArticleCard key={a.id} article={a} rank={i + 1} selected={sel.has(a.id)} editable={editable} onToggle={toggle} disableSelect={atMax} />
        ))}
      </ul>
    </div>
  );
}
