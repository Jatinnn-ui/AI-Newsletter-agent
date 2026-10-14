import { useId, useState } from "react";
import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { Select } from "../ui/Select";
import { cx } from "../ui/cx";

export interface ResearchSettingsValue {
  topic: string;
  audience: string;
  articleCount: number | null;
  lookbackDays: number | null;
}

export const ARTICLE_COUNTS = [3, 4, 5, 6, 7];
export const LOOKBACK_OPTIONS = [1, 3, 7, 14, 30];

/** Inline form fields, reused by the composer and the Settings page. */
export function ResearchFields({ value, onChange, idPrefix }: { value: ResearchSettingsValue; onChange: (patch: Partial<ResearchSettingsValue>) => void; idPrefix: string }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <label htmlFor={`${idPrefix}-topic`} className="mb-1.5 block text-[12px] font-medium text-fg-2">
          Topic <span className="font-normal text-fg-3">· optional</span>
        </label>
        <input
          id={`${idPrefix}-topic`}
          className="field h-9"
          maxLength={120}
          placeholder="Inferred from the goal"
          value={value.topic}
          onChange={(e) => onChange({ topic: e.target.value })}
        />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-audience`} className="mb-1.5 block text-[12px] font-medium text-fg-2">
          Audience <span className="font-normal text-fg-3">· optional</span>
        </label>
        <input
          id={`${idPrefix}-audience`}
          className="field h-9"
          maxLength={120}
          placeholder="e.g. AI engineers"
          value={value.audience}
          onChange={(e) => onChange({ audience: e.target.value })}
        />
      </div>
      <fieldset>
        <legend className="mb-1.5 text-[12px] font-medium text-fg-2">Number of articles</legend>
        <div role="radiogroup" aria-label="Number of articles" className="flex gap-1 rounded-[8px] border border-line-subtle bg-input p-0.5">
          {ARTICLE_COUNTS.map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={value.articleCount === n}
              onClick={() => onChange({ articleCount: n })}
              className={cx(
                "transition-base mono h-7 flex-1 rounded-[6px] text-[12px]",
                value.articleCount === n ? "bg-elevated text-fg shadow-[inset_0_0_0_1px_var(--border-default)]" : "text-fg-3 hover:text-fg-2",
              )}
            >
              {n}
            </button>
          ))}
        </div>
      </fieldset>
      <div>
        <label htmlFor={`${idPrefix}-lookback`} className="mb-1.5 block text-[12px] font-medium text-fg-2">
          Lookback period
        </label>
        <Select id={`${idPrefix}-lookback`} value={value.lookbackDays ?? 7} onChange={(e) => onChange({ lookbackDays: Number(e.target.value) })}>
          {LOOKBACK_OPTIONS.map((d) => (
            <option key={d} value={d}>
              Last {d} {d === 1 ? "day" : "days"}
            </option>
          ))}
        </Select>
      </div>
    </div>
  );
}

export function ResearchSettings({ value, onChange }: { value: ResearchSettingsValue; onChange: (patch: Partial<ResearchSettingsValue>) => void }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const summary = [
    `${value.articleCount ?? 5} articles`,
    `${value.lookbackDays ?? 7}d lookback`,
    value.topic.trim() && `topic: ${value.topic.trim()}`,
    value.audience.trim() && `for ${value.audience.trim()}`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="rounded-[10px] border border-line-subtle">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className="transition-base flex w-full items-center gap-2.5 rounded-[10px] px-3 py-2.5 text-left hover:bg-elevated/50"
      >
        <SlidersHorizontal size={14} strokeWidth={1.75} className="text-fg-3" aria-hidden />
        <span className="text-[13px] text-fg">Research settings</span>
        <span className="mono min-w-0 flex-1 truncate text-[11px] text-fg-3">{summary}</span>
        <ChevronDown size={15} className={cx("transition-base text-fg-3", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div id={id} className="border-t border-line-subtle px-3 pt-3 pb-4">
          <ResearchFields value={value} onChange={onChange} idPrefix="rs" />
        </div>
      )}
    </div>
  );
}
