import { createContext, useCallback, useContext, useEffect, useMemo, useState, type AnchorHTMLAttributes, type MouseEvent, type ReactNode } from "react";

// A small History API router. The app has five routes, so a routing dependency isn't worth it.

export type Route =
  | { name: "overview" }
  | { name: "history" }
  | { name: "run"; runId: string; tab: string | null }
  | { name: "newsletters" }
  | { name: "settings" }
  | { name: "not_found" };

function parse(pathname: string, search: string): Route {
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/") return { name: "overview" };
  if (path === "/runs") return { name: "history" };
  if (path === "/newsletters") return { name: "newsletters" };
  if (path === "/settings") return { name: "settings" };
  const m = path.match(/^\/runs\/([a-f0-9]{32})$/);
  if (m) return { name: "run", runId: m[1], tab: new URLSearchParams(search).get("tab") };
  return { name: "not_found" };
}

interface RouterValue {
  route: Route;
  navigate: (to: string, opts?: { replace?: boolean }) => void;
}

const RouterContext = createContext<RouterValue | null>(null);

export function RouterProvider({ children }: { children: ReactNode }) {
  const [loc, setLoc] = useState(() => ({ path: location.pathname, search: location.search }));

  useEffect(() => {
    const onPop = () => setLoc({ path: location.pathname, search: location.search });
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback((to: string, opts?: { replace?: boolean }) => {
    const url = new URL(to, location.origin);
    if (url.pathname + url.search === location.pathname + location.search) return;
    history[opts?.replace ? "replaceState" : "pushState"](null, "", url.pathname + url.search);
    setLoc({ path: url.pathname, search: url.search });
    if (!opts?.replace) window.scrollTo({ top: 0 });
  }, []);

  const value = useMemo(() => ({ route: parse(loc.path, loc.search), navigate }), [loc, navigate]);
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function useRouter() {
  const ctx = useContext(RouterContext);
  if (!ctx) throw new Error("useRouter outside RouterProvider");
  return ctx;
}

export const paths = {
  overview: "/",
  history: "/runs",
  run: (id: string, tab?: string) => `/runs/${id}${tab ? `?tab=${tab}` : ""}`,
  newsletters: "/newsletters",
  settings: "/settings",
};

/** Anchor that navigates client-side but keeps real hrefs (open in new tab, copy link). */
export function Link({ to, onClick, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  const { navigate } = useRouter();
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(to);
  };
  return <a href={to} onClick={handle} {...rest} />;
}
