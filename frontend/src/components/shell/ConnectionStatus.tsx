import { useHealth } from "../../hooks/useHealth";
import { cx } from "../ui/cx";

export function ConnectionDot({ className }: { className?: string }) {
  const { connection } = useHealth();
  return (
    <span
      aria-hidden
      className={cx(
        "inline-block h-2 w-2 shrink-0 rounded-full",
        connection === "online" ? "bg-ok" : connection === "offline" ? "bg-err" : "pulse bg-fg-3",
        className,
      )}
    />
  );
}

export function connectionText(connection: string, demoOnly: boolean) {
  if (connection === "online") return demoOnly ? "API connected · demo only" : "API connected";
  if (connection === "offline") return "API unreachable";
  return "Checking API…";
}

/** Compact pill for page headers. */
export function ConnectionStatus() {
  const { connection, health, recheck } = useHealth();
  const demoOnly = Boolean(health && !health.config.live_mode_available);
  return (
    <button
      type="button"
      onClick={recheck}
      title="Check backend connection"
      className="transition-base inline-flex h-8 items-center gap-2 rounded-full border border-line-subtle bg-surface px-3 text-[12px] text-fg-2 hover:border-line hover:text-fg"
    >
      <ConnectionDot />
      <span role="status">{connectionText(connection, demoOnly)}</span>
    </button>
  );
}
