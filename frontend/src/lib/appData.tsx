// App-wide data: integration status (polled) and the public catalog (fetched once).
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, errorText } from "../api/client";
import type { Catalog, CheckResult, StatusResponse } from "../api/types";

interface AppData {
  status: StatusResponse | null;
  statusError: string | null;
  statusLoading: boolean;
  refreshStatus: () => Promise<void>;
  checking: boolean;
  checkError: string | null;
  checkConnection: () => Promise<CheckResult | null>;
  catalog: Catalog | null;
  catalogError: string | null;
  reloadCatalog: () => void;
}

const Ctx = createContext<AppData | null>(null);

const STATUS_POLL_MS = 10_000;

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogNonce, setCatalogNonce] = useState(0);
  const inflight = useRef(false);

  const refreshStatus = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = true;
    try {
      const s = await api.status();
      setStatus(s);
      setStatusError(null);
    } catch (e) {
      setStatusError(errorText(e));
    } finally {
      inflight.current = false;
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
    const t = window.setInterval(() => void refreshStatus(), STATUS_POLL_MS);
    return () => window.clearInterval(t);
  }, [refreshStatus]);

  useEffect(() => {
    let alive = true;
    api.catalog().then(
      (c) => {
        if (!alive) return;
        setCatalog(c);
        setCatalogError(null);
      },
      (e) => {
        if (alive) setCatalogError(errorText(e));
      },
    );
    return () => {
      alive = false;
    };
  }, [catalogNonce]);

  // When the backend comes back, retry the catalog automatically.
  useEffect(() => {
    if (status && !catalog && catalogError) setCatalogNonce((n) => n + 1);
  }, [status, catalog, catalogError]);

  const checkConnection = useCallback(async () => {
    setChecking(true);
    setCheckError(null);
    try {
      const res = await api.checkConnection();
      await refreshStatus();
      return res;
    } catch (e) {
      setCheckError(errorText(e));
      return null;
    } finally {
      setChecking(false);
    }
  }, [refreshStatus]);

  const reloadCatalog = useCallback(() => setCatalogNonce((n) => n + 1), []);

  return (
    <Ctx.Provider
      value={{
        status,
        statusError,
        statusLoading,
        refreshStatus,
        checking,
        checkError,
        checkConnection,
        catalog,
        catalogError,
        reloadCatalog,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAppData(): AppData {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAppData outside provider");
  return v;
}
