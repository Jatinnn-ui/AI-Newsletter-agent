import { useEffect, useMemo, useState, type FormEvent } from "react";
import { FlaskConical, Play, Sparkles } from "lucide-react";
import { useHealth } from "../../hooks/useHealth";
import { api, ApiError, errorMessage } from "../../lib/api";
import { usePreferences } from "../../lib/prefs";
import { paths, useRouter } from "../../lib/router";
import type { ExecutionMode, StartRunBody } from "../../lib/types";
import { Button } from "../ui/Button";
import { cx } from "../ui/cx";
import { ErrorState } from "../ui/States";
import { ExecutionModeSelector } from "./ExecutionModeSelector";
import { ResearchSettings, type ResearchSettingsValue } from "./ResearchSettings";

const MAX = 2000;
const EXAMPLES = [
  { label: "AI agent industry updates", goal: "Create a weekly newsletter covering the latest AI agent news, product launches and funding from the past week." },
  { label: "Generative AI research", goal: "Summarize the most important generative AI research papers and model releases from the last week for ML engineers." },
  { label: "Developer tools and launches", goal: "Write a newsletter about new AI developer tools, IDE features and SDK launches that matter to software teams." },
];

/** Mirrors the backend GoalInput validator so users see problems before submitting. */
export function validateGoal(goal: string): string | null {
  const cleaned = goal.trim().replace(/\s+/g, " ");
  if (!cleaned) return "Describe the newsletter you want the agent to create.";
  if (cleaned.length < 10) return "Goal is too short. Use at least 10 characters.";
  if ((cleaned.match(/[A-Za-z]/g) ?? []).length < 5) return "Goal must contain a readable description.";
  if (goal.length > MAX) return `Goal must be ${MAX} characters or fewer.`;
  return null;
}

// Draft survives navigation within the session (e.g. visiting Settings and coming back).
let draftGoal = "";

export function GoalComposer() {
  const { prefs } = usePreferences();
  const { health, connection } = useHealth();
  const { navigate } = useRouter();

  const [goal, setGoal] = useState(draftGoal);
  const [mode, setMode] = useState<ExecutionMode>(prefs.mode);
  const [settings, setSettings] = useState<ResearchSettingsValue>({
    topic: prefs.topic,
    audience: prefs.audience,
    articleCount: prefs.articleCount,
    lookbackDays: prefs.lookbackDays,
  });
  const [demo, setDemo] = useState(false);
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<ApiError | Error | null>(null);

  useEffect(() => {
    draftGoal = goal;
  }, [goal]);

  const cfg = health?.config;
  const serverForcesDemo = Boolean(cfg?.deterministic_mode);
  const demoAllowed = Boolean(cfg && (cfg.deterministic_runs_allowed || cfg.deterministic_mode));
  const liveAvailable = Boolean(cfg?.live_mode_available);
  // If live research isn't configured, demo mode is the only option the server will accept.
  const useDemo = serverForcesDemo || demo || (!liveAvailable && demoAllowed);

  const validation = useMemo(() => validateGoal(goal), [goal]);
  const showValidation = touched && validation;
  const blocked = connection === "online" && cfg && !liveAvailable && !demoAllowed;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (validation || submitting) {
      if (validation) document.getElementById("goal")?.focus();
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    const body: StartRunBody = {
      goal: goal.trim(),
      mode,
      topic: settings.topic.trim() || null,
      audience: settings.audience.trim() || null,
      article_count: settings.articleCount,
      lookback_days: settings.lookbackDays,
      deterministic: useDemo && !serverForcesDemo ? true : false,
    };
    try {
      const run = await api.startRun(body);
      draftGoal = "";
      navigate(paths.run(run.run_id));
    } catch (err) {
      setSubmitError(err instanceof Error ? err : new Error(errorMessage(err)));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="panel overflow-hidden" aria-labelledby="composer-title">
      <div className="px-5 pt-5 pb-4 sm:px-6 sm:pt-6">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <h2 id="composer-title" className="text-[19px] font-medium tracking-[-0.015em] text-fg">
              What should I research?
            </h2>
            <p className="mt-1 text-[13px] text-fg-2">Describe your newsletter goal in plain English. The agent will handle research, writing and review.</p>
          </div>
          <Sparkles size={16} strokeWidth={1.75} className="mt-1 hidden text-accent sm:block" aria-hidden />
        </div>

        <div className="mt-4">
          <label htmlFor="goal" className="sr-only">
            Newsletter goal
          </label>
          <div className={cx("rounded-[10px] border bg-input transition-base focus-within:border-accent focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent-primary)_16%,transparent)]", showValidation ? "border-err" : "border-line")}>
            <textarea
              id="goal"
              name="goal"
              rows={4}
              maxLength={MAX}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              onBlur={() => goal && setTouched(true)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit(e as unknown as FormEvent);
              }}
              placeholder="Create a weekly newsletter covering the latest AI agent news, product launches and research."
              aria-invalid={showValidation ? true : undefined}
              aria-describedby="goal-help goal-count"
              className="block min-h-[112px] w-full resize-y bg-transparent px-3.5 pt-3 pb-2 text-[15px] leading-relaxed text-fg placeholder:text-fg-3 focus:outline-none"
            />
            <div className="flex items-center gap-2 px-3.5 pb-2.5">
              <p id="goal-help" className={cx("min-w-0 flex-1 text-[12px]", showValidation ? "text-err" : "text-fg-3")} aria-live="polite">
                {showValidation ? validation : <span className="hidden sm:inline">Press Ctrl/⌘ + Enter to run</span>}
              </p>
              <span id="goal-count" className={cx("mono text-[11px]", goal.length > MAX * 0.9 ? "text-warn" : "text-fg-3")}>
                {goal.length}/{MAX}
              </span>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[12px] text-fg-3">Try</span>
            {EXAMPLES.map((ex) => (
              <button
                key={ex.label}
                type="button"
                onClick={() => {
                  setGoal(ex.goal);
                  setTouched(false);
                  document.getElementById("goal")?.focus();
                }}
                className="transition-base h-7 rounded-full border border-line-subtle bg-elevated/60 px-3 text-[12px] text-fg-2 hover:border-line hover:text-fg"
              >
                {ex.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-4 border-t border-line-subtle px-5 py-4 sm:px-6">
        <ExecutionModeSelector value={mode} onChange={setMode} />
        <ResearchSettings value={settings} onChange={(p) => setSettings((s) => ({ ...s, ...p }))} />
      </div>

      {submitError && (
        <div className="px-5 pb-4 sm:px-6">
          <ErrorState
            title={submitError instanceof ApiError && submitError.offline ? "Backend unreachable" : "Couldn't start the run"}
            message={submitError.message}
          >
            {submitError instanceof ApiError && submitError.offline && <StartBackendHint />}
          </ErrorState>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-line-subtle bg-sidebar/60 px-5 py-3 sm:px-6">
        {demoAllowed && (
          <label className={cx("inline-flex items-center gap-2 text-[12px]", serverForcesDemo || !liveAvailable ? "text-fg-3" : "text-fg-2")}>
            <input
              type="checkbox"
              name="demo"
              checked={useDemo}
              disabled={serverForcesDemo || !liveAvailable}
              onChange={(e) => setDemo(e.target.checked)}
              className="h-3.5 w-3.5 accent-[var(--accent-primary)]"
            />
            <FlaskConical size={13} strokeWidth={1.75} aria-hidden />
            Demo mode · offline fixture data
            {(serverForcesDemo || !liveAvailable) && <span className="text-fg-3">({serverForcesDemo ? "server is in deterministic mode" : "live research not configured"})</span>}
          </label>
        )}
        {blocked && <p className="text-[12px] text-warn">The backend has no Gemini/Tavily keys and demo runs are disabled.</p>}
        <Button type="submit" variant="primary" icon={Play} loading={submitting} disabled={Boolean(blocked)} className="ml-auto min-w-[132px]">
          {submitting ? "Starting…" : "Run Agent"}
        </Button>
      </div>
    </form>
  );
}

export function StartBackendHint() {
  return (
    <div className="mt-3 text-[12px] text-fg-2">
      <p>Start the API from the backend folder, then retry:</p>
      <pre className="mono mt-1.5 overflow-x-auto rounded-md border border-line-subtle bg-input px-3 py-2 text-[12px] text-fg">
        uvicorn app.main:app --reload --port 8000
      </pre>
    </div>
  );
}
