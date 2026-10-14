import { History, LayoutGrid, Mail, PanelLeftClose, PanelLeftOpen, Plus, Settings } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useHealth } from "../../hooks/useHealth";
import { API_BASE } from "../../lib/api";
import { Link, paths, useRouter, type Route } from "../../lib/router";
import { cx } from "../ui/cx";
import { ConnectionDot, connectionText } from "./ConnectionStatus";
import { LogoMark } from "./Logo";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  match: (r: Route) => boolean;
}

const primaryNav: NavItem[] = [
  { to: paths.overview, label: "Overview", icon: LayoutGrid, match: (r) => r.name === "overview" },
  { to: paths.history, label: "Run History", icon: History, match: (r) => r.name === "history" || r.name === "run" },
  { to: paths.newsletters, label: "Newsletters", icon: Mail, match: (r) => r.name === "newsletters" },
];
const settingsNav: NavItem = { to: paths.settings, label: "Settings", icon: Settings, match: (r) => r.name === "settings" };

function NavLink({ item, collapsed, onNavigate }: { item: NavItem; collapsed: boolean; onNavigate?: () => void }) {
  const { route } = useRouter();
  const active = item.match(route);
  const Icon = item.icon;
  return (
    <Link
      to={item.to}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      title={collapsed ? item.label : undefined}
      className={cx(
        "transition-base flex h-8 items-center gap-2.5 rounded-[7px] px-2.5 text-[13px]",
        active ? "bg-accent-soft text-fg" : "text-fg-2 hover:bg-elevated hover:text-fg",
        collapsed && "justify-center px-0",
      )}
    >
      <Icon size={16} strokeWidth={1.75} className={active ? "text-accent" : "text-fg-3"} aria-hidden />
      {!collapsed && <span className="truncate">{item.label}</span>}
      {collapsed && <span className="sr-only">{item.label}</span>}
    </Link>
  );
}

export function Sidebar({
  collapsed,
  onToggle,
  onNavigate,
  mobile,
}: {
  collapsed: boolean;
  onToggle?: () => void;
  onNavigate?: () => void;
  mobile?: boolean;
}) {
  const { connection, health } = useHealth();
  const { navigate } = useRouter();
  const host = API_BASE ? API_BASE.replace(/^https?:\/\//, "") : "same origin";
  const demoOnly = Boolean(health && !health.config.live_mode_available);

  return (
    <nav aria-label="Primary" className="flex h-full flex-col bg-sidebar">
      <div className={cx("flex h-[var(--header-height)] items-center gap-2.5 px-4", collapsed && "justify-center px-0")}>
        <LogoMark />
        {!collapsed && (
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-[14px] font-medium tracking-[-0.01em] text-fg">Newsletter Agent</p>
            <p className="mono truncate text-[11px] text-fg-3">local workspace</p>
          </div>
        )}
        {!mobile && !collapsed && onToggle && (
          <button
            type="button"
            onClick={onToggle}
            aria-label="Collapse sidebar"
            title="Collapse sidebar"
            className="transition-base -mr-1.5 rounded-md p-1.5 text-fg-3 hover:bg-elevated hover:text-fg"
          >
            <PanelLeftClose size={16} strokeWidth={1.75} aria-hidden />
          </button>
        )}
      </div>

      <div className={cx("px-3 pt-1 pb-3", collapsed && "px-2")}>
        <button
          type="button"
          onClick={() => {
            navigate(paths.overview);
            onNavigate?.();
            window.setTimeout(() => document.getElementById("goal")?.focus(), 0);
          }}
          title={collapsed ? "New Run" : undefined}
          className={cx(
            "transition-base flex h-8 w-full items-center gap-2 rounded-[8px] border border-line bg-elevated px-2.5 text-[13px] text-fg hover:border-fg-3/60",
            collapsed && "justify-center px-0",
          )}
        >
          <Plus size={15} strokeWidth={2} className="text-accent" aria-hidden />
          {!collapsed ? <span>New Run</span> : <span className="sr-only">New Run</span>}
          {!collapsed && <kbd className="mono ml-auto text-[10px] text-fg-3">N</kbd>}
        </button>
      </div>

      <div className={cx("flex flex-col gap-0.5 px-3", collapsed && "px-2")}>
        {!collapsed && <p className="eyebrow px-2.5 pt-2 pb-1.5">Workspace</p>}
        {primaryNav.map((item) => (
          <NavLink key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} />
        ))}
      </div>

      <div className={cx("mt-auto flex flex-col gap-0.5 px-3 pb-3", collapsed && "px-2")}>
        <NavLink item={settingsNav} collapsed={collapsed} onNavigate={onNavigate} />
        <div
          className={cx("mt-2 flex items-center gap-2.5 rounded-[8px] border border-line-subtle px-2.5 py-2", collapsed && "justify-center border-0 px-0")}
          title={`${connectionText(connection, demoOnly)} · ${host}`}
        >
          <ConnectionDot />
          {!collapsed && (
            <div className="min-w-0 leading-tight">
              <p className="truncate text-[12px] text-fg-2">{connectionText(connection, demoOnly)}</p>
              <p className="mono truncate text-[11px] text-fg-3">{host}</p>
            </div>
          )}
          {collapsed && <span className="sr-only">{connectionText(connection, demoOnly)}</span>}
        </div>
        {!mobile && collapsed && onToggle && (
          <button
            type="button"
            onClick={onToggle}
            aria-label="Expand sidebar"
            title="Expand sidebar"
            className="transition-base mt-1 flex h-8 items-center justify-center rounded-md text-fg-3 hover:bg-elevated hover:text-fg"
          >
            <PanelLeftOpen size={16} strokeWidth={1.75} aria-hidden />
          </button>
        )}
      </div>
    </nav>
  );
}
