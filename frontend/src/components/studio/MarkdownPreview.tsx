import { memo, useMemo, useState } from "react";
import { renderMarkdown } from "../../lib/markdown";
import { Segmented } from "../ui/Tabs";

/** Markdown shown either rendered (as React elements, never innerHTML) or as raw source text. */
export const MarkdownPreview = memo(function MarkdownPreview({ markdown }: { markdown: string }) {
  const [view, setView] = useState<"rendered" | "source">("rendered");
  const rendered = useMemo(() => renderMarkdown(markdown), [markdown]);
  return (
    <div className="overflow-hidden rounded-[10px] border border-line-subtle">
      <div className="flex items-center gap-2 border-b border-line-subtle bg-surface px-3 py-2">
        <span className="mono text-[11px] text-fg-3">{markdown.split("\n").length} lines</span>
        <div className="ml-auto">
          <Segmented
            label="Markdown view"
            value={view}
            onChange={setView}
            options={[
              { value: "rendered", label: "Rendered" },
              { value: "source", label: "Source" },
            ]}
          />
        </div>
      </div>
      {view === "rendered" ? (
        <article className="prose-editorial max-h-[78vh] overflow-y-auto bg-white px-6 py-8 sm:px-10">{rendered}</article>
      ) : (
        <pre className="mono max-h-[78vh] overflow-auto bg-input p-4 text-[12px] leading-relaxed whitespace-pre-wrap text-fg-2">{markdown}</pre>
      )}
    </div>
  );
});
