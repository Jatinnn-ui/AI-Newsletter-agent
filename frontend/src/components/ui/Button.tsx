import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2, type LucideIcon } from "lucide-react";
import { cx } from "./cx";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: LucideIcon;
  iconRight?: LucideIcon;
  loading?: boolean;
  children?: ReactNode;
}

const variants: Record<Variant, string> = {
  primary:
    "bg-accent text-accent-contrast font-medium hover:bg-accent-hover disabled:bg-accent/40 disabled:text-accent-contrast/70",
  secondary:
    "bg-elevated text-fg border border-line hover:border-fg-3/60 hover:bg-[#272a32] disabled:text-fg-3 disabled:hover:border-line disabled:hover:bg-elevated",
  ghost: "text-fg-2 hover:text-fg hover:bg-elevated disabled:text-fg-3 disabled:hover:bg-transparent",
  danger:
    "text-err border border-err/30 bg-err/5 hover:bg-err/10 hover:border-err/50 disabled:opacity-50",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5",
  md: "h-9 px-4 text-sm gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", icon: Icon, iconRight: IconRight, loading, disabled, className, children, type = "button", ...rest },
  ref,
) {
  const iconSize = size === "sm" ? 14 : 16;
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(
        "transition-base inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-[var(--radius-control)] select-none disabled:cursor-not-allowed",
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 size={iconSize} className="spin" aria-hidden /> : Icon ? <Icon size={iconSize} strokeWidth={1.75} aria-hidden /> : null}
      {children}
      {IconRight && !loading ? <IconRight size={iconSize} strokeWidth={1.75} aria-hidden /> : null}
    </button>
  );
});

export function IconButton({
  icon: Icon,
  label,
  className,
  size = 16,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { icon: LucideIcon; label: string; size?: number }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cx(
        "transition-base inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-control)] text-fg-3 hover:bg-elevated hover:text-fg disabled:opacity-40 disabled:hover:bg-transparent",
        className,
      )}
      {...rest}
    >
      <Icon size={size} strokeWidth={1.75} aria-hidden />
    </button>
  );
}
