import { useState, type FormEvent } from "react";
import { Check, KeyRound, RotateCw, X } from "lucide-react";
import { ExecutionModeSelector } from "../components/composer/ExecutionModeSelector";
import { ResearchFields, type ResearchSettingsValue } from "../components/composer/ResearchSettings";
import { StartBackendHint } from "../components/composer/GoalComposer";
import { PageContainer, PageHeader } from "../components/shell/AppShell";
import { Button } from "../components/ui/Button";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { Badge } from "../components/ui/StatusBadge";
import { ErrorState, LoadingState } from "../components/ui/States";
import { useToast } from "../components/ui/Toast";
import { useHealth } from "../hooks/useHealth";
import { API_BASE, getToken, setToken } from "../lib/api";
import { fmtRelative } from "../lib/format";
import { usePreferences } from "../lib/prefs";
import type { ExecutionMode } from "../lib/types";

function Row({ label, ok, children }: { label: string; ok?: boolean; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5">
      {ok === undefined ? (
        <span className="w-3.5" aria-hidden />
      ) : ok ? (
        <Check size={14} strokeWidth={2.25} className="text-ok" aria-label="Available" />
      ) : (
        <X size={14} strokeWidth={2.25} className="text-err" aria-label="Unavailable" />
      )}
      <dt className="shrink-0 text-[13px] text-fg-2">{label}</dt>
      <dd className="mono ml-auto min-w-0 text-right text-[12px] break-words text-fg">{children}</dd>
    </div>
  );
}

function ServerStatus() {
  const { health, connection, error, checkedAt, recheck } = useHealth();
  const c = health?.config;
  return (
    <Panel aria-labelledby="server-h">
      <PanelHeader
        id="server-h"
        title="Backend"
        description="Read from GET /api/health. Server configuration is set in the backend .env and can't be changed here."
        actions={
          <Button size="sm" variant="ghost" icon={RotateCw} onClick={recheck}>
            Check
          </Button>
        }
      />
      {connection === "offline" ? (
        <div className="p-4">
          <ErrorState title={`Can't reach ${API_BASE || "this origin"}`} message={error ?? "Connection failed."}>
            <StartBackendHint />
          </ErrorState>
        </div>
      ) : !c || !health ? (
        <LoadingState label="Checking backend…" />
      ) : (
        <dl className="divide-y divide-line-subtle">
          <Row label="Connection" ok>
            {API_BASE || "same origin"} · v{health.version}
          </Row>
          <Row label="Language model" ok={c.llm_configured}>
            {c.llm_configured ? `${c.llm_provider} · ${c.llm_model}` : "not configured"}
          </Row>
          <Row label="Web search" ok={c.search_configured}>
            {c.search_configured ? c.search_provider : "not configured"}
          </Row>
          <Row label="Live research runs" ok={c.live_mode_available}>
            {c.live_mode_available ? "available" : "unavailable"}
          </Row>
          <Row label="Demo (fixture) runs" ok={c.deterministic_runs_allowed || c.deterministic_mode}>
            {c.deterministic_mode ? "forced on server" : c.deterministic_runs_allowed ? "allowed" : "disabled"}
          </Row>
          <Row label="Access token required">{c.auth_required ? "yes" : "no"}</Row>
          <Row label="Review pass threshold">{c.review_pass_threshold}</Row>
          <Row label="Max automatic revisions">{c.max_revisions}</Row>
          <Row label="Delivery">simulated (saved to disk)</Row>
          <Row label="Active runs">
            {health.runs.active} / {health.runs.max_concurrent} concurrent
          </Row>
          <Row label="Environment">{c.environment}</Row>
          <Row label="Last checked">{checkedAt ? fmtRelative(new Date(checkedAt).toISOString()) : "—"}</Row>
        </dl>
      )}
    </Panel>
  );
}

function AccessToken() {
  const { health, recheck } = useHealth();
  const toast = useToast();
  const [value, setValue] = useState("");
  const [hasToken, setHasToken] = useState(Boolean(getToken()));
  if (!health?.config.auth_required && !hasToken) return null;

  return (
    <Panel aria-labelledby="token-h">
      <PanelHeader
        id="token-h"
        title="Workspace access token"
        description="This backend protects its API with API_AUTH_TOKEN. The token is kept in this tab's sessionStorage and cleared when the tab closes. Never paste Gemini or Tavily keys here."
      />
      <form
        className="flex flex-col gap-2 p-4 sm:flex-row"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setToken(value.trim());
          setHasToken(Boolean(value.trim()));
          setValue("");
          recheck();
          toast({ tone: "success", title: "Access token saved for this session" });
        }}
      >
        <label htmlFor="token" className="sr-only">
          Access token
        </label>
        <div className="relative flex-1">
          <KeyRound size={14} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-fg-3" aria-hidden />
          <input id="token" type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} placeholder={hasToken ? "Token set for this session" : "Paste the API_AUTH_TOKEN value"} className="field h-9 pl-9" />
        </div>
        <Button type="submit" variant="primary" disabled={!value.trim()}>
          Save
        </Button>
        {hasToken && (
          <Button
            variant="ghost"
            onClick={() => {
              setToken("");
              setHasToken(false);
              toast({ tone: "info", title: "Access token cleared" });
            }}
          >
            Clear
          </Button>
        )}
      </form>
    </Panel>
  );
}

function Defaults() {
  const { prefs, update, reset } = usePreferences();
  const toast = useToast();
  const [mode, setMode] = useState<ExecutionMode>(prefs.mode);
  const [research, setResearch] = useState<ResearchSettingsValue>({
    topic: prefs.topic,
    audience: prefs.audience,
    articleCount: prefs.articleCount,
    lookbackDays: prefs.lookbackDays,
  });
  const dirty =
    mode !== prefs.mode || research.topic !== prefs.topic || research.audience !== prefs.audience || research.articleCount !== prefs.articleCount || research.lookbackDays !== prefs.lookbackDays;

  return (
    <Panel aria-labelledby="defaults-h">
      <PanelHeader id="defaults-h" title="Run defaults" description="Frontend preferences, saved in this browser's localStorage. They prefill the goal composer and are not sent to the server until you start a run." />
      <form
        className="space-y-5 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          update({ mode, ...research });
          toast({ tone: "success", title: "Defaults saved" });
        }}
      >
        <ExecutionModeSelector value={mode} onChange={setMode} name="default-mode" />
        <ResearchFields value={research} onChange={(p) => setResearch((r) => ({ ...r, ...p }))} idPrefix="def" />
        <div className="flex flex-wrap justify-end gap-2 border-t border-line-subtle pt-4">
          <Button
            variant="ghost"
            onClick={() => {
              reset();
              setMode("autonomous");
              setResearch({ topic: "", audience: "", articleCount: 5, lookbackDays: 7 });
              toast({ tone: "info", title: "Defaults reset" });
            }}
          >
            Reset
          </Button>
          <Button type="submit" variant="primary" disabled={!dirty}>
            Save defaults
          </Button>
        </div>
      </form>
    </Panel>
  );
}

export function SettingsPage() {
  const { health } = useHealth();
  return (
    <PageContainer>
      <PageHeader
        eyebrow="Workspace / Settings"
        title="Settings"
        description="Connection status and defaults for new runs."
        actions={health?.config.delivery_mode === "simulated" ? <Badge tone="neutral">Simulated delivery</Badge> : undefined}
      />
      <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <ServerStatus />
          <AccessToken />
        </div>
        <Defaults />
      </div>
    </PageContainer>
  );
}
