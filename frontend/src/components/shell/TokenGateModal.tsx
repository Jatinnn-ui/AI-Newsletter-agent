import { useEffect, useState } from "react";
import { KeyRound } from "lucide-react";
import { api, ApiError, getToken, setToken } from "../../lib/api";
import { useHealth } from "../../hooks/useHealth";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { useToast } from "../ui/Toast";

/**
 * Shown automatically on load when the backend requires an API token
 * (health.config.auth_required) and none is stored for this tab yet.
 * The token is validated against a protected endpoint before the modal closes,
 * so a wrong token is caught immediately instead of failing on the first run.
 */
export function TokenGateModal() {
  const { health, recheck } = useHealth();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Open once the first health check resolves and we see auth is required with no token set.
  useEffect(() => {
    if (health?.config.auth_required && !getToken()) setOpen(true);
  }, [health]);

  const save = async () => {
    const token = value.trim();
    if (!token) return;
    setSaving(true);
    setError(null);
    setToken(token);
    try {
      // listRuns is a protected route: a wrong token returns 401 here.
      await api.listRuns(1);
      setValue("");
      setOpen(false);
      recheck();
      toast({ tone: "success", title: "Access token saved for this session" });
    } catch (e) {
      // Roll back the bad token so the next attempt starts clean.
      setToken("");
      const invalid = e instanceof ApiError && (e.status === 401 || e.status === 403);
      setError(invalid ? "That token was rejected by the backend. Check the value and try again." : "Could not verify the token. Is the backend reachable?");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={() => setOpen(false)}
      title="Access token required"
      description="This backend protects its API with API_AUTH_TOKEN. Paste the token to continue. It is kept in this tab's sessionStorage only and cleared when the tab closes. Never paste a Gemini or Tavily key here."
      footer={
        <Button variant="primary" loading={saving} disabled={!value.trim()} onClick={() => void save()}>
          Save and continue
        </Button>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <label htmlFor="gate-token" className="sr-only">
          Access token
        </label>
        <div className="relative">
          <KeyRound size={14} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-fg-3" aria-hidden />
          <input
            id="gate-token"
            type="password"
            autoComplete="off"
            autoFocus
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              if (error) setError(null);
            }}
            placeholder="Paste the API_AUTH_TOKEN value"
            aria-invalid={error ? true : undefined}
            className="field field-icon h-9"
          />
        </div>
        {error && <p className="mt-2 text-[12px] text-err">{error}</p>}
        {/* Submit on Enter without a visible duplicate button. */}
        <button type="submit" className="sr-only" aria-hidden tabIndex={-1} />
      </form>
    </Dialog>
  );
}
