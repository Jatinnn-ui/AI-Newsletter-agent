import { Bot, UserCheck } from "lucide-react";
import type { ExecutionMode } from "../../lib/types";
import { cx } from "../ui/cx";

const MODES: { value: ExecutionMode; title: string; description: string; icon: typeof Bot }[] = [
  { value: "autonomous", title: "Fully autonomous", description: "Plan, research, write and review automatically.", icon: Bot },
  {
    value: "human_in_the_loop",
    title: "Human-in-the-loop",
    description: "Approve article selection and review the newsletter before saving.",
    icon: UserCheck,
  },
];

export function ExecutionModeSelector({ value, onChange, name = "mode" }: { value: ExecutionMode; onChange: (m: ExecutionMode) => void; name?: string }) {
  return (
    <fieldset>
      <legend className="mb-2 text-[12px] font-medium text-fg-2">Execution mode</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {MODES.map((m) => {
          const active = m.value === value;
          const Icon = m.icon;
          return (
            <label
              key={m.value}
              className={cx(
                "transition-base relative flex cursor-pointer items-start gap-3 rounded-[10px] border p-3 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent",
                active ? "border-accent/60 bg-accent-soft" : "border-line-subtle bg-input hover:border-line",
              )}
            >
              <input
                type="radio"
                name={name}
                value={m.value}
                checked={active}
                onChange={() => onChange(m.value)}
                className="sr-only"
              />
              <span
                aria-hidden
                className={cx(
                  "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
                  active ? "border-accent" : "border-fg-3/70",
                )}
              >
                {active && <span className="h-2 w-2 rounded-full bg-accent" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className={cx("mono text-[11px] tracking-[0.06em] uppercase", active ? "text-fg" : "text-fg-2")}>{m.title}</span>
                  <Icon size={14} strokeWidth={1.75} className={cx("ml-auto", active ? "text-accent" : "text-fg-3")} aria-hidden />
                </span>
                <span className="mt-1 block text-[13px] leading-snug text-fg-3">{m.description}</span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
