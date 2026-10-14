import type { ReactNode } from "react";
import { cx } from "./cx";

export function Panel({ children, className, as: Tag = "section", ...rest }: { children: ReactNode; className?: string; as?: "section" | "div" | "aside" } & React.HTMLAttributes<HTMLElement>) {
  return (
    <Tag className={cx("panel min-w-0", className)} {...rest}>
      {children}
    </Tag>
  );
}

export function PanelHeader({ title, description, actions, id, className }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; id?: string; className?: string }) {
  return (
    <header className={cx("flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line-subtle px-4 py-3", className)}>
      <div className="min-w-0 flex-1">
        <h2 id={id} className="text-[14px] font-medium text-fg">
          {title}
        </h2>
        {description && <p className="mt-0.5 text-[12px] text-fg-3">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** Key/value line used for run and newsletter metadata. */
export function Meta({ label, children, mono }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-[12px] text-fg-3">{label}</dt>
      <dd className={cx("mt-0.5 truncate text-[13px] text-fg", mono && "mono text-[12px]")}>{children}</dd>
    </div>
  );
}
