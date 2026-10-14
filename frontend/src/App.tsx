import { useEffect } from "react";
import { Compass } from "lucide-react";
import { AppShell, PageContainer } from "./components/shell/AppShell";
import { EmptyState } from "./components/ui/States";
import { ToastProvider } from "./components/ui/Toast";
import { HealthProvider } from "./hooks/useHealth";
import { Link, paths, RouterProvider, useRouter } from "./lib/router";
import { HistoryPage } from "./pages/HistoryPage";
import { NewslettersPage } from "./pages/NewslettersPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RunPage } from "./pages/RunPage";
import { SettingsPage } from "./pages/SettingsPage";

const titles = { overview: "Overview", history: "Run History", run: "Run", newsletters: "Newsletters", settings: "Settings", not_found: "Not found" };

function Routes() {
  const { route } = useRouter();
  useEffect(() => {
    document.title = `${titles[route.name]} · Newsletter Agent`;
  }, [route.name]);

  switch (route.name) {
    case "overview":
      return <OverviewPage />;
    case "history":
      return <HistoryPage />;
    case "run":
      return <RunPage key={route.runId} runId={route.runId} initialTab={route.tab} />;
    case "newsletters":
      return <NewslettersPage />;
    case "settings":
      return <SettingsPage />;
    default:
      return (
        <PageContainer>
          <EmptyState
            icon={Compass}
            title="Page not found"
            action={
              <Link to={paths.overview} className="text-[13px] text-accent hover:underline">
                Go to overview
              </Link>
            }
            className="panel py-16"
          />
        </PageContainer>
      );
  }
}

export default function App() {
  return (
    <RouterProvider>
      <HealthProvider>
        <ToastProvider>
          <AppShell>
            <Routes />
          </AppShell>
        </ToastProvider>
      </HealthProvider>
    </RouterProvider>
  );
}
