// Tiny hash router: #/, #/runs, #/run/:id, #/run/:id/replay, #/twin, #/blind,
// #/guided, #/guided/:id, #/about.
import { useEffect, useState } from "react";

export type Route =
  | { name: "runs" }
  | { name: "run"; id: string; replay: boolean }
  | { name: "twin" }
  | { name: "blind" }
  | { name: "guided"; id: string | null }
  | { name: "about" }
  | { name: "notfound"; path: string };

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, "").replace(/\?.*$/, "") || "/";
  let parts: string[];
  try {
    parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  } catch {
    // malformed percent-escape (e.g. a truncated link): show "not found" instead of crashing
    return { name: "notfound", path };
  }
  if (parts.length === 0) return { name: "runs" };
  const [head, a, b] = parts;
  switch (head) {
    case "runs":
      return parts.length === 1 ? { name: "runs" } : { name: "notfound", path };
    case "run":
      if (a && (parts.length === 2 || (parts.length === 3 && b === "replay")))
        return { name: "run", id: a, replay: b === "replay" };
      return { name: "notfound", path };
    case "twin":
      return { name: "twin" };
    case "blind":
      return { name: "blind" };
    case "guided":
      return { name: "guided", id: a ?? null };
    case "about":
      return { name: "about" };
    default:
      return { name: "notfound", path };
  }
}

export function navigate(path: string): void {
  const target = path.startsWith("#") ? path : `#${path}`;
  if (window.location.hash === target) return;
  window.location.hash = target;
}

export function runHref(id: string, replay = false): string {
  return `#/run/${encodeURIComponent(id)}${replay ? "/replay" : ""}`;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash(window.location.hash));
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
