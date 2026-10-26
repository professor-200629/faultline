import { useEffect, useRef } from "react";
import { DisconnectedBanner, TopBar } from "./components/TopBar";
import { EmptyState } from "./components/common";
import { AppDataProvider } from "./lib/appData";
import { useRoute, type Route } from "./lib/router";
import { AboutPage } from "./pages/About";
import { BlindChallengePage } from "./pages/BlindChallenge";
import { GuidedIntro } from "./pages/Guided";
import { RunsPage } from "./pages/Runs";
import { TwinChallengePage } from "./pages/TwinChallenge";
import { Workstation } from "./pages/Workstation";

function titleFor(r: Route): string {
  switch (r.name) {
    case "runs":
      return "Investigations";
    case "run":
      return r.replay ? `Replay ${r.id}` : `Run ${r.id}`;
    case "twin":
      return "Twin Challenge";
    case "blind":
      return "Blind Challenge";
    case "guided":
      return "Guided example";
    case "about":
      return "About";
    default:
      return "Not found";
  }
}

function Page({ route }: { route: Route }) {
  switch (route.name) {
    case "runs":
      return <RunsPage />;
    case "run":
      return <Workstation key={`${route.id}:${route.replay}`} id={route.id} replay={route.replay} />;
    case "twin":
      return <TwinChallengePage />;
    case "blind":
      return <BlindChallengePage />;
    case "guided":
      return route.id ? <Workstation key={`g:${route.id}`} id={route.id} replay={false} guide /> : <GuidedIntro />;
    case "about":
      return <AboutPage />;
    default:
      return (
        <div className="page">
          <EmptyState title="Page not found">
            <p>
              Nothing at <span className="mono">#{route.path}</span>. <a href="#/">Go to the run list</a>.
            </p>
          </EmptyState>
        </div>
      );
  }
}

export default function App() {
  const route = useRoute();
  const fill = route.name === "run" || (route.name === "guided" && !!route.id);
  useEffect(() => {
    document.title = `${titleFor(route)} · FAULTLINE`;
  }, [route]);
  // After a navigation that removed the focused control (e.g. picking a twin), focus would
  // fall to <body>; put it at the start of the new page's content instead.
  const firstRoute = useRef(true);
  useEffect(() => {
    if (firstRoute.current) {
      firstRoute.current = false;
      return;
    }
    const active = document.activeElement;
    if (!active || active === document.body || !active.isConnected) document.getElementById("main")?.focus({ preventScroll: true });
  }, [route]);
  return (
    <AppDataProvider>
      <div className="app" data-fill={fill ? "true" : "false"}>
        <button type="button" className="skip-link" onClick={() => document.getElementById("main")?.focus()}>
          Skip to content
        </button>
        <TopBar route={route} />
        <DisconnectedBanner />
        <main id="main" tabIndex={-1}>
          <Page route={route} />
        </main>
      </div>
    </AppDataProvider>
  );
}
