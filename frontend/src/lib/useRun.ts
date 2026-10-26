// Loads a run and keeps it fresh.
// Polls GET /api/runs/:id?after=<last seq> every ~700 ms while the run is ready or
// investigating (merging new events), refreshes telemetry while investigating,
// polls slowly while awaiting approval, and stops once the run is terminal.
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorText } from "../api/client";
import type { RunEvent, RunView, Telemetry } from "../api/types";
import { isTerminal } from "./runModel";

const FAST_MS = 700;
const SLOW_MS = 4000;
const RETRY_MS = 2000;
const TELEMETRY_MIN_GAP_MS = 1400;
/** Retries after a failed refresh even when the run is terminal (e.g. the refresh after a reveal). */
const REFRESH_RETRIES = 3;

export interface RunState {
  view: RunView | null;
  events: RunEvent[];
  telemetry: Telemetry | null;
  telemetryError: string | null;
  loading: boolean;
  error: string | null;
  pollError: string | null;
  /** True while a failed poll/refresh will be retried automatically. */
  pollRetrying: boolean;
  /** Re-fetches the run now; resolves with the fresh view, or null if the fetch failed. */
  refresh: () => Promise<RunView | null>;
}

function mergeEvents(prev: RunEvent[], incoming: RunEvent[]): RunEvent[] {
  if (!incoming.length) return prev;
  const last = prev.length ? prev[prev.length - 1].seq : 0;
  const fresh = incoming.filter((e) => e.seq > last).sort((a, b) => a.seq - b.seq);
  return fresh.length ? [...prev, ...fresh] : prev;
}

export function useRun(id: string, poll: boolean): RunState {
  const [view, setView] = useState<RunView | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [telemetryError, setTelemetryError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [pollRetrying, setPollRetrying] = useState(false);

  const gen = useRef(0);
  const lastSeq = useRef(0);
  const timer = useRef<number | null>(null);
  const inflight = useRef(false);
  const lastTelemetryAt = useRef(0);
  const statusRef = useRef<string>("");
  const retriesLeft = useRef(0);

  const clearTimer = () => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  };

  const fetchTelemetry = useCallback(async (g: number) => {
    lastTelemetryAt.current = Date.now();
    try {
      const t = await api.telemetry(id);
      if (g !== gen.current) return;
      setTelemetry(t);
      setTelemetryError(null);
    } catch (e) {
      if (g !== gen.current) return;
      setTelemetryError(errorText(e));
    }
  }, [id]);

  const schedule = useCallback(
    (g: number, delay: number, fn: () => void) => {
      clearTimer();
      if (g !== gen.current) return;
      timer.current = window.setTimeout(fn, delay);
    },
    [],
  );

  const tick = useCallback(async (g: number): Promise<RunView | null> => {
    if (g !== gen.current || inflight.current) return null;
    inflight.current = true;
    try {
      const v = await api.run(id, lastSeq.current);
      if (g !== gen.current) return null;
      const prevStatus = statusRef.current;
      statusRef.current = v.status;
      const incoming = v.events ?? [];
      setEvents((prev) => mergeEvents(prev, incoming));
      if (incoming.length) lastSeq.current = Math.max(lastSeq.current, ...incoming.map((e) => e.seq));
      setView(v);
      setPollError(null);
      setPollRetrying(false);
      retriesLeft.current = 0;
      const changed = prevStatus !== v.status;
      const newWork = incoming.some((e) => e.type === "tool_result" || e.type === "status");
      const stale = Date.now() - lastTelemetryAt.current > TELEMETRY_MIN_GAP_MS;
      if (v.status === "investigating" ? newWork || stale : changed || newWork) void fetchTelemetry(g);
      if (poll && !isTerminal(v.status)) {
        const delay = v.status === "awaiting_approval" ? SLOW_MS : FAST_MS;
        schedule(g, delay, () => void tick(g));
      }
      return v;
    } catch (e) {
      if (g !== gen.current) return null;
      setPollError(errorText(e));
      // Keep polling an active run; after an explicit refresh retry a few times even if terminal.
      const retry = poll && (!isTerminal(statusRef.current) || retriesLeft.current > 0);
      if (retry && isTerminal(statusRef.current)) retriesLeft.current--;
      setPollRetrying(retry);
      if (retry) schedule(g, RETRY_MS, () => void tick(g));
      return null;
    } finally {
      inflight.current = false;
    }
  }, [id, poll, fetchTelemetry, schedule]);

  useEffect(() => {
    const g = ++gen.current;
    lastSeq.current = 0;
    statusRef.current = "";
    inflight.current = false;
    setView(null);
    setEvents([]);
    setTelemetry(null);
    setTelemetryError(null);
    setError(null);
    setPollError(null);
    setPollRetrying(false);
    retriesLeft.current = 0;
    setLoading(true);
    (async () => {
      try {
        const v = await api.run(id, 0);
        if (g !== gen.current) return;
        const evs = [...(v.events ?? [])].sort((a, b) => a.seq - b.seq);
        lastSeq.current = evs.length ? evs[evs.length - 1].seq : 0;
        statusRef.current = v.status;
        setEvents(evs);
        setView(v);
        setLoading(false);
        void fetchTelemetry(g);
        if (poll && !isTerminal(v.status)) {
          schedule(g, v.status === "awaiting_approval" ? SLOW_MS : FAST_MS, () => void tick(g));
        }
      } catch (e) {
        if (g !== gen.current) return;
        setError(errorText(e));
        setLoading(false);
      }
    })();
    return () => {
      gen.current++;
      clearTimer();
    };
  }, [id, poll, fetchTelemetry, schedule, tick]);

  const refresh = useCallback(async (): Promise<RunView | null> => {
    const g = gen.current;
    clearTimer();
    retriesLeft.current = REFRESH_RETRIES;
    // wait for an in-flight poll to settle so the after= cursor is current
    for (let i = 0; i < 20 && inflight.current; i++) await new Promise((r) => window.setTimeout(r, 50));
    const v = await tick(g);
    void fetchTelemetry(g);
    return v;
  }, [tick, fetchTelemetry]);

  return { view, events, telemetry, telemetryError, loading, error, pollError, pollRetrying, refresh };
}
