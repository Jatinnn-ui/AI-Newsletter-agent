// Types mirror backend/app/api/schemas.py and backend/app/models/domain.py.

export type ExecutionMode = "autonomous" | "human_in_the_loop";

export type RunStatus =
  | "queued"
  | "running"
  | "awaiting_research_approval"
  | "awaiting_draft_approval"
  | "completed"
  | "completed_with_warnings"
  | "failed"
  | "cancelled"
  | "expired";

export const TERMINAL_STATUSES: RunStatus[] = ["completed", "completed_with_warnings", "failed", "cancelled", "expired"];
export const isTerminal = (s: RunStatus) => TERMINAL_STATUSES.includes(s);
export const isAwaiting = (s: RunStatus) => s === "awaiting_research_approval" || s === "awaiting_draft_approval";

export type StageName = "planning" | "research" | "selection" | "summarization" | "writing" | "review" | "revision" | "output";
export type StageStatus = "pending" | "running" | "completed" | "skipped" | "failed" | "waiting" | "cancelled";
export type LogLevel = "info" | "running" | "success" | "warning" | "error" | "approval";

export interface HealthConfig {
  environment: string;
  llm_provider: string;
  llm_model: string;
  llm_fallback_models: string[];
  llm_configured: boolean;
  search_provider: string;
  search_configured: boolean;
  deterministic_mode: boolean;
  deterministic_runs_allowed: boolean;
  live_mode_available: boolean;
  max_revisions: number;
  review_pass_threshold: number;
  delivery_mode: "simulated";
  auth_required: boolean;
}

export interface HealthResponse {
  status: "ok";
  version: string;
  time: string;
  config: HealthConfig;
  runs: { active: number; max_concurrent: number };
}

export interface StartRunBody {
  goal: string;
  mode: ExecutionMode;
  topic?: string | null;
  audience?: string | null;
  article_count?: number | null;
  lookback_days?: number | null;
  deterministic?: boolean;
}

export interface RunSummary {
  run_id: string;
  status: RunStatus;
  mode: ExecutionMode;
  deterministic: boolean;
  goal: string;
  current_stage: string | null;
  created_at: string;
  updated_at: string;
  error: string | null;
}

export interface PlanTask {
  id: string;
  stage: StageName;
  title: string;
  description: string;
}

export interface ExecutionPlan {
  normalized_goal: string;
  summary: string;
  tasks: PlanTask[];
  research_queries: string[];
  output_requirements: string[];
  assumptions: string[];
  config: {
    topic: string;
    audience: string;
    article_count: number;
    lookback_days: number;
    cadence: string;
    title_hint: string;
  };
  planner: "llm" | "heuristic" | "heuristic_fallback" | "deterministic";
}

export interface Article {
  id: string;
  title: string;
  url: string;
  normalized_url: string;
  publisher: string;
  domain: string;
  snippet: string;
  published_date: string | null;
  date_source: "search_api" | "page_metadata" | null;
  date_note: string | null;
  search_query: string | null;
  search_score: number | null;
  relevance_score: number;
  recency_score: number;
  source_quality: number;
  final_score: number;
  rank_reasons: string[];
  content: string | null;
  content_basis: "full_text" | "search_snippet";
  retrieval_status: "not_attempted" | "retrieved" | "failed" | "skipped";
  retrieval_note: string | null;
  duplicates_merged: string[];
  is_test_data: boolean;
}

export interface NewsletterSection {
  article_id: string;
  headline: string;
  summary: string;
  why_it_matters: string;
  key_facts: string[];
  source_url: string;
  publisher: string;
  published_date: string | null;
  date_source: "search_api" | "page_metadata" | null;
  content_basis: "full_text" | "search_snippet";
}

export interface NewsletterDraft {
  subject: string;
  preheader: string;
  title: string;
  intro: string;
  sections: NewsletterSection[];
  closing: string;
  generated_at: string;
  limitations: string[];
  is_test_data: boolean;
  version: number;
}

export interface ReviewCheck {
  id: string;
  label: string;
  passed: boolean;
  score: number;
  weight: number;
  details: string;
}

export interface ReviewIssue {
  id: string;
  check_id: string;
  severity: "critical" | "major" | "minor";
  message: string;
  suggestion: string;
  article_id: string | null;
  correctable: boolean;
}

export interface ReviewResult {
  attempt: number;
  score: number;
  threshold: number;
  passed: boolean;
  revision_required: boolean;
  checks: ReviewCheck[];
  issues: ReviewIssue[];
  summary: string;
  reviewer: string;
  reviewed_at: string;
}

export interface RevisionRecord {
  attempt: number;
  trigger: "critic" | "user";
  feedback: string | null;
  issues_addressed: string[];
  changes: string[];
  score_before: number | null;
  score_after: number | null;
  created_at: string;
}

export interface ToolCallRecord {
  id: string;
  tool: string;
  stage: string | null;
  input_summary: string;
  status: "running" | "success" | "error" | "fallback";
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  result_summary: string | null;
  error: string | null;
}

export interface LogEntry {
  timestamp: string;
  stage: string | null;
  level: LogLevel;
  message: string;
  data: Record<string, unknown>;
}

export interface SavedOutput {
  html_path: string;
  markdown_path: string;
  html_filename: string;
  markdown_filename: string;
  saved_at: string;
}

export interface ApprovalInfo {
  kind: "research" | "draft";
  requested_at: string;
  user_revisions_used: number;
  user_revisions_max: number;
}

export interface RunMetrics {
  duration_seconds: number | null;
  article_count: number;
  candidate_count: number;
  tool_call_count: number;
  review_score: number | null;
  review_passed: boolean | null;
  revision_count: number;
}

export interface RunDetail {
  run_id: string;
  status: RunStatus;
  mode: ExecutionMode;
  deterministic: boolean;
  goal: string;
  request: Partial<StartRunBody>;
  current_stage: string | null;
  stages: Partial<Record<StageName, StageStatus>>;
  created_at: string;
  updated_at: string;
  error: string | null;
  approval: ApprovalInfo | null;
  plan: ExecutionPlan | null;
  candidates: Article[];
  proposed_ids: string[];
  selected_ids: string[];
  draft: NewsletterDraft | null;
  html: string | null;
  markdown: string | null;
  review: ReviewResult | null;
  reviews: ReviewResult[];
  revisions: RevisionRecord[];
  warnings: string[];
  limitations: string[];
  output: SavedOutput | null;
  logs: LogEntry[];
  tool_calls: ToolCallRecord[];
  metrics: RunMetrics;
  delivery_mode: "simulated";
  last_event_id: number;
}
