import { memo } from "react";
import { cx } from "../ui/cx";

/**
 * Renders generated newsletter HTML in a fully sandboxed iframe via srcdoc.
 * No allow-scripts and no allow-same-origin: the document cannot run code or touch the app.
 * Popups are allowed so source links can open in a new tab, escaping the sandbox
 * (the new page gets a normal browsing context, still without access to this app).
 *
 * Fills its container height so the newsletter stays the focal point; falls back to a tall
 * fixed height when the parent is not height-constrained.
 */
export const NewsletterPreview = memo(function NewsletterPreview({ html, width, reloadKey }: { html: string; width: "desktop" | "mobile"; reloadKey: number }) {
  return (
    <div className="flex h-full min-h-[560px] justify-center overflow-auto bg-elevated p-0 sm:p-4">
      <iframe
        key={reloadKey}
        title="Newsletter HTML preview"
        srcDoc={html}
        sandbox="allow-popups allow-popups-to-escape-sandbox"
        referrerPolicy="no-referrer"
        loading="lazy"
        className={cx(
          "block h-full min-h-[540px] rounded-none border-0 bg-white sm:rounded-[6px] sm:shadow-[0_1px_3px_rgba(0,0,0,0.12)]",
          width === "mobile" ? "w-[390px] max-w-full" : "w-full",
        )}
      />
    </div>
  );
});
