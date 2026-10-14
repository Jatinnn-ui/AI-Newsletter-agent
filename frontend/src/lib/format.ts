import type { ExecutionMode, RunStatus, StageName } from "./types";

const dateTime = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
const dateOnly = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" });
const timeOnly = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });

const valid = (d: Date) => !Number.isNaN(d.getTime());

export function fmtDateTime(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  return valid(d) ? dateTime.format(d) : "—";
}

export function fmtTime(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  return valid(d) ? timeOnly.format(d) : "—";
}

/** Formats YYYY-MM-DD as a calendar date without timezone drift. */
export function fmtDay(day: string | null | undefined) {
  if (!day) return null;
  const m = day.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return day;
  return dateOnly.format(new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
}

export function fmtRelative(iso: string | null | undefined, now = Date.now()) {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.round((now - t) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  if (s < 86400 * 7) return `${Math.round(s / 86400)}d ago`;
  return fmtDateTime(iso);
}

export function fmtDuration(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export const fmtMs = (ms: number | null | undefined) => (ms == null ? null : fmtDuration(ms / 1000));

export const shortId = (id: string) => id.slice(0, 8);

export const modeLabel: Record<ExecutionMode, string> = {
  autonomous: "Autonomous",
  human_in_the_loop: "Human-in-the-loop",
};

export const statusLabel: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  awaiting_research_approval: "Needs approval",
  awaiting_draft_approval: "Needs approval",
  completed: "Completed",
  completed_with_warnings: "Completed with warnings",
  failed: "Failed",
  cancelled: "Cancelled",
  expired: "Expired",
};

export const stageMeta: Record<StageName, { label: string; description: string }> = {
  planning: { label: "Planning", description: "Interpret the goal and plan research queries." },
  research: { label: "Research", description: "Search the web and retrieve candidate articles." },
  selection: { label: "Article selection", description: "Rank, de-duplicate and pick the strongest stories." },
  summarization: { label: "Summarization", description: "Summarize each article from its source text." },
  writing: { label: "Newsletter writing", description: "Draft the subject, intro and story sections." },
  review: { label: "Self-review", description: "Score the draft against quality checks." },
  revision: { label: "Revision", description: "Address reviewer issues, when required." },
  output: { label: "Final output", description: "Render HTML and Markdown and save the files." },
};

export const STAGES = Object.keys(stageMeta) as StageName[];

export const toolLabel = (tool: string) =>
  tool
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

export function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Only http(s) links from research data are rendered as clickable. */
export function safeHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}

export function truncate(text: string, max: number) {
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}
