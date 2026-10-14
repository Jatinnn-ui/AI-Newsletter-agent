import { forwardRef, type SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";
import { cx } from "./cx";

/**
 * Native <select> with the browser arrow hidden (appearance-none) and a single Lucide
 * chevron overlaid, matching the rest of the design system. Using an overlaid icon avoids
 * background-image tiling that happens when the `.field` background shorthand resets
 * background-size/repeat on the element.
 */
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <div className="relative inline-flex w-full">
      <select
        ref={ref}
        className={cx(
          "field h-9 w-full appearance-none bg-none pr-8 text-[13px]",
          "[&::-ms-expand]:hidden",
          className,
        )}
        {...rest}
      >
        {children}
      </select>
      <ChevronDown
        size={15}
        strokeWidth={1.75}
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-fg-3"
      />
    </div>
  );
});
