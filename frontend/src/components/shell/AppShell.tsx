import { useEffect, useRef, useState, type ReactNode } from "react";
import { Menu, X } from "lucide-react";
import { usePreferences } from "../../lib/prefs";
import { paths, useRouter } from "../../lib/router";
import { cx } from "../ui/cx";
import { ConnectionDot } from "./ConnectionStatus";
import { LogoMark } from "./Logo";
import { Sidebar } from "./Sidebar";
import { TokenGateModal } from "./TokenGateModal";

export function AppShell({ children }: { children: ReactNode }) {
  const { prefs, update } = usePreferences();
  const { route, navigate } = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawer = useRef<HTMLDialogElement>(null);
  const collapsed = prefs.sidebarCollapsed;

  // Close the drawer on navigation.
  useEffect(() => setDrawerOpen(false), [route]);

  useEffect(() => {
    const el = drawer.current;
    if (!el) return;
    if (drawerOpen && !el.open) el.showModal();
    if (!drawerOpen && el.open) el.close();
  }, [drawerOpen]);

  // "N" starts a new run from anywhere outside a text field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "n" || e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [contenteditable='true'], dialog[open]")) return;
      e.preventDefault();
      navigate(paths.overview);
      window.setTimeout(() => document.getElementById("goal")?.focus(), 0);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  return (
    <div className="flex min-h-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-elevated focus:px-3 focus:py-2">
        Skip to content
      </a>

      {/* Desktop / tablet sidebar */}
      <aside
        className={cx(
          "sticky top-0 hidden h-screen shrink-0 border-r border-line-subtle transition-[width] duration-200 md:block",
          collapsed ? "w-[var(--sidebar-collapsed)]" : "w-[var(--sidebar-width)]",
        )}
      >
        <Sidebar collapsed={collapsed} onToggle={() => update({ sidebarCollapsed: !collapsed })} />
      </aside>

      {/* Mobile drawer */}
      <dialog
        ref={drawer}
        aria-label="Navigation"
        onClose={() => setDrawerOpen(false)}
        onClick={(e) => e.target === drawer.current && setDrawerOpen(false)}
        className="m-0 h-full max-h-none w-[min(280px,85vw)] border-r border-line bg-sidebar p-0 text-fg backdrop:bg-black/60 md:hidden"
      >
        <div className="relative h-full">
          <button
            type="button"
            aria-label="Close navigation"
            onClick={() => setDrawerOpen(false)}
            className="absolute top-3 right-3 z-10 rounded-md p-1.5 text-fg-3 hover:bg-elevated hover:text-fg"
          >
            <X size={16} aria-hidden />
          </button>
          <Sidebar collapsed={false} mobile onNavigate={() => setDrawerOpen(false)} />
        </div>
      </dialog>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-[var(--header-height)] items-center gap-3 border-b border-line-subtle bg-canvas/95 px-4 backdrop-blur md:hidden">
          <button
            type="button"
            aria-label="Open navigation"
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(true)}
            className="-ml-1.5 rounded-md p-1.5 text-fg-2 hover:bg-elevated hover:text-fg"
          >
            <Menu size={18} aria-hidden />
          </button>
          <LogoMark size={20} />
          <span className="text-[14px] font-medium">Newsletter Agent</span>
          <ConnectionDot className="ml-auto" />
        </header>
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 focus:outline-none">
          {children}
        </main>
      </div>

      <TokenGateModal />
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end gap-x-6 gap-y-4 pb-6">
      <div className="min-w-0 flex-1">
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="mt-2 text-[26px] leading-tight font-semibold tracking-[-0.025em] text-fg sm:text-[30px]">{title}</h1>
        {description && <p className="mt-1.5 text-[14px] text-fg-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function PageContainer({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return <div className={cx("mx-auto w-full px-4 py-6 sm:px-6 lg:px-8 lg:py-8", wide ? "max-w-[1440px]" : "max-w-[1180px]")}>{children}</div>;
}
