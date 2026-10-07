"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError, errorMessage, isUnauthorized, type User } from "../lib/api";
import type { StudyToday } from "../learning/study-types";

export type StudySession = {
  id: string;
  status: "active" | "paused" | "completed" | "abandoned";
  revision: number;
  started_at: string;
  updated_at: string;
  ended_at: string | null;
  active_seconds: number;
  as_of: string;
  focus: StudyToday["focus"];
  estimated_minutes: number;
  target_minutes: number;
  idle_timeout_seconds: number;
};

type SessionAction = "start" | "pause" | "resume" | "finish" | "abandon" | "heartbeat";
type SessionContext = {
  session: StudySession | null;
  elapsedSeconds: number;
  ownerId: string | null;
  accountScope: string | null;
  eligible: boolean;
  loading: boolean;
  busy: boolean;
  error: string;
  startBlocked: boolean;
  requiresAction: boolean;
  historyRevision: number;
  refresh: () => Promise<void>;
  action: (action: Exclude<SessionAction, "heartbeat">) => Promise<void>;
  clear: () => void;
};

const StudySessionContext = createContext<SessionContext | null>(null);
const APP_PATHS = ["/dashboard", "/learning", "/projects", "/jobs", "/account", "/billing", "/assessment"];
const REQUEST_TIMEOUT_SECONDS = 15;
const REQUEST_TIMEOUT_MESSAGE = "Сервер не ответил вовремя. Таймер не продолжает отсчёт без связи дольше минуты. Обновите занятие и попробуйте снова.";

function isWorkspacePath(path: string) {
  return APP_PATHS.some((prefix) => path === prefix || path.startsWith(`${prefix}/`));
}

export function studyDuration(seconds: number) {
  const bounded = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(bounded / 3600);
  const minutes = Math.floor((bounded % 3600) / 60);
  const remainder = String(bounded % 60).padStart(2, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${remainder}`
    : `${String(minutes).padStart(2, "0")}:${remainder}`;
}

export default function StudySessionProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const workspacePath = isWorkspacePath(pathname);
  const [session, setSession] = useState<StudySession | null>(null);
  const [ownerId, setOwnerId] = useState<string | null>(null);
  const [accountScope, setAccountScope] = useState<string | null>(null);
  const [eligible, setEligible] = useState(false);
  const [loading, setLoading] = useState(workspacePath);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [startBlocked, setStartBlocked] = useState(false);
  const [requiresAction, setRequiresAction] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [historyRevision, setHistoryRevision] = useState(0);
  const sessionRef = useRef<StudySession | null>(null);
  const ownerRef = useRef<string | null>(null);
  const scopeRef = useRef<string | null>(null);
  const eligibleRef = useRef(false);
  const busyRef = useRef(false);
  const loadingRef = useRef(workspacePath);
  const automaticPulseBlocked = useRef(false);
  const receivedAt = useRef(0);
  const generation = useRef(0);
  const controllers = useRef(new Set<AbortController>());
  const queue = useRef<Promise<void>>(Promise.resolve());

  const abortRequests = useCallback(() => {
    generation.current += 1;
    controllers.current.forEach((controller) => controller.abort());
    controllers.current.clear();
    queue.current = Promise.resolve();
    busyRef.current = false;
    setBusy(false);
  }, []);

  const clear = useCallback(() => {
    abortRequests();
    sessionRef.current = null;
    ownerRef.current = null;
    scopeRef.current = null;
    eligibleRef.current = false;
    loadingRef.current = false;
    setSession(null);
    setOwnerId(null);
    setAccountScope(null);
    setEligible(false);
    setLoading(false);
    setError("");
    setStartBlocked(false);
    automaticPulseBlocked.current = false;
    setRequiresAction(false);
    setElapsedSeconds(0);
    setHistoryRevision((value) => value + 1);
  }, [abortRequests]);

  const receive = useCallback((next: StudySession | null) => {
    sessionRef.current = next;
    receivedAt.current = performance.now();
    setSession(next);
    setElapsedSeconds(next?.active_seconds ?? 0);
  }, []);

  const refresh = useCallback(async (accountRetry = false): Promise<void> => {
    abortRequests();
    if (!workspacePath) {
      clear();
      return;
    }
    const requestGeneration = generation.current;
    const controller = new AbortController();
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, REQUEST_TIMEOUT_SECONDS * 1000);
    controllers.current.add(controller);
    loadingRef.current = true;
    setLoading(true);
    setError("");
    setStartBlocked(false);
    // Hide the previous account's projection while checking the actual session.
    ownerRef.current = null;
    scopeRef.current = null;
    eligibleRef.current = false;
    setOwnerId(null);
    setAccountScope(null);
    setEligible(false);
    receive(null);
    try {
      const user = await api<User>("/me", { signal: controller.signal, cache: "no-store" });
      if (controller.signal.aborted || generation.current !== requestGeneration) return;
      if (typeof user.account_scope !== "string" || user.account_scope.length !== 64) {
        setError("Не удалось подтвердить аккаунт. Обновите занятие и попробуйте снова.");
        return;
      }
      ownerRef.current = user.id;
      scopeRef.current = user.account_scope;
      setOwnerId(user.id);
      setAccountScope(user.account_scope);
      const canStudy = Boolean(user.profile?.onboarding_completed);
      eligibleRef.current = canStudy;
      setEligible(canStudy);
      if (!canStudy) return;
      const result = await api<{ session: StudySession | null }>("/learning/study-session", {
        signal: controller.signal,
        cache: "no-store",
        headers: { "X-Account-Scope": user.account_scope },
      });
      if (controller.signal.aborted || generation.current !== requestGeneration) return;
      receive(result.session);
      setHistoryRevision((value) => value + 1);
    } catch (reason) {
      if (generation.current !== requestGeneration || (controller.signal.aborted && !timedOut)) return;
      if (timedOut) {
        setError(REQUEST_TIMEOUT_MESSAGE);
        return;
      }
      if (isUnauthorized(reason)) {
        clear();
        router.replace("/auth");
      } else if (reason instanceof ApiError && reason.code === "account_changed") {
        clear();
        automaticPulseBlocked.current = true;
        setRequiresAction(true);
        if (!accountRetry) void refresh(true);
        else setError("Аккаунт изменился во время загрузки. Обновите занятие перед продолжением.");
      } else {
        setError(errorMessage(reason));
      }
    } finally {
      window.clearTimeout(timeout);
      controllers.current.delete(controller);
      if (generation.current === requestGeneration) {
        loadingRef.current = false;
        setLoading(false);
      }
    }
  }, [abortRequests, clear, receive, router, workspacePath]);

  const mutate = useCallback((action: SessionAction, keepalive = false): Promise<void> => {
    if (!workspacePath || !ownerRef.current || !scopeRef.current || !eligibleRef.current || loadingRef.current) {
      return Promise.resolve();
    }
    const requestGeneration = generation.current;
    const requestOwner = ownerRef.current;
    const requestScope = scopeRef.current;
    busyRef.current = true;
    setBusy(true);
    const task = queue.current.then(async () => {
      if (generation.current !== requestGeneration || ownerRef.current !== requestOwner || scopeRef.current !== requestScope) return;
      const current = sessionRef.current;
      if (action !== "start" && !current) return;
      if (action === "heartbeat" && (automaticPulseBlocked.current || current?.status !== "active" || document.visibilityState !== "visible")) return;
      if (action === "pause" && current?.status !== "active") return;
      const controller = new AbortController();
      let timedOut = false;
      const timeout = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, REQUEST_TIMEOUT_SECONDS * 1000);
      controllers.current.add(controller);
      if (action !== "heartbeat") setError("");
      try {
        const path = action === "start"
          ? "/learning/study-sessions/start"
          : `/learning/study-sessions/${encodeURIComponent(current!.id)}/${action}`;
        const result = await api<StudySession>(path, {
          method: "POST",
          body: JSON.stringify(action === "start" ? {} : { expected_revision: current!.revision }),
          signal: controller.signal,
          keepalive,
          cache: "no-store",
          headers: { "X-Account-Scope": requestScope },
        });
        if (controller.signal.aborted || generation.current !== requestGeneration || ownerRef.current !== requestOwner || scopeRef.current !== requestScope) return;
        receive(result);
        if (action !== "heartbeat") {
          automaticPulseBlocked.current = false;
          setRequiresAction(false);
        }
        if (result.status === "completed" || result.status === "abandoned") {
          setHistoryRevision((value) => value + 1);
        }
      } catch (reason) {
        if (generation.current !== requestGeneration || ownerRef.current !== requestOwner || scopeRef.current !== requestScope || (controller.signal.aborted && !timedOut)) return;
        if (timedOut) {
          setError(REQUEST_TIMEOUT_MESSAGE);
          return;
        }
        if (isUnauthorized(reason)) {
          clear();
          router.replace("/auth");
        } else if (reason instanceof ApiError && reason.code === "account_changed") {
          clear();
          automaticPulseBlocked.current = true;
          setRequiresAction(true);
          void refresh();
        } else if (reason instanceof ApiError && (reason.status === 403 || reason.status === 404)) {
          clear();
          void refresh();
        } else if (reason instanceof ApiError && reason.status === 409) {
          automaticPulseBlocked.current = true;
          setRequiresAction(true);
          let latest: { session: StudySession | null };
          try {
            latest = await api<{ session: StudySession | null }>("/learning/study-session", {
              signal: controller.signal,
              cache: "no-store",
              headers: { "X-Account-Scope": requestScope },
            });
          } catch (loadReason) {
            if (generation.current !== requestGeneration || ownerRef.current !== requestOwner) return;
            if (isUnauthorized(loadReason)) {
              clear();
              router.replace("/auth");
            } else if (loadReason instanceof ApiError && loadReason.code === "account_changed") {
              clear();
              automaticPulseBlocked.current = true;
              setRequiresAction(true);
              void refresh();
            } else {
              receive(null);
              setError(timedOut ? REQUEST_TIMEOUT_MESSAGE : "Состояние занятия изменилось, но загрузить его сейчас не удалось. Обновите занятие перед продолжением.");
            }
            return;
          }
          if (controller.signal.aborted || generation.current !== requestGeneration || ownerRef.current !== requestOwner) return;
          receive(latest.session);
          setHistoryRevision((value) => value + 1);
          if (action === "start" && !latest.session) setStartBlocked(true);
          setError(action === "resume" && (latest.session?.active_seconds ?? 0) >= 8 * 3600
            ? "Занятие достигло лимита 8 часов по таймеру. Завершите его, затем можно начать новое."
            : action === "start" && !latest.session
            ? "Сейчас нет доступного плана занятия. Откройте программу курса или завершите настройку обучения."
            : latest.session?.status === "active"
              ? "Занятие изменилось в другой вкладке или на другом устройстве. Эта вкладка не продлевает таймер автоматически. Нажмите «Пауза», затем продолжите занятие вручную."
              : "Занятие изменилось в другой вкладке или на другом устройстве. Мы загрузили актуальное состояние. Продолжение нужно выбрать вручную.");
        } else {
          setError(errorMessage(reason));
        }
      } finally {
        window.clearTimeout(timeout);
        controllers.current.delete(controller);
      }
    });
    const settled = task.catch(() => undefined);
    queue.current = settled;
    return task.finally(() => {
      if (generation.current === requestGeneration && queue.current === settled) {
        busyRef.current = false;
        setBusy(false);
      }
    });
  }, [clear, receive, refresh, router, workspacePath]);

  useEffect(() => {
    void refresh();
    return abortRequests;
  }, [pathname, refresh, abortRequests]);

  useEffect(() => {
    const onAuthChanged = () => {
      clear();
      if (workspacePath) {
        automaticPulseBlocked.current = true;
        setRequiresAction(true);
        void refresh();
      }
    };
    window.addEventListener("mentor:auth-changed", onAuthChanged);
    return () => window.removeEventListener("mentor:auth-changed", onAuthChanged);
  }, [clear, refresh, workspacePath]);

  useEffect(() => {
    if (!workspacePath) return;
    const pauseWhenLeaving = () => {
      if (sessionRef.current?.status === "active") void mutate("pause", true);
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") pauseWhenLeaving();
      else void refresh();
    };
    const onFocus = () => {
      if (document.visibilityState === "visible" && !loadingRef.current && !busyRef.current) void refresh();
    };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", pauseWhenLeaving);
    window.addEventListener("focus", onFocus);
    const heartbeat = window.setInterval(() => {
      if (document.visibilityState === "visible" && !automaticPulseBlocked.current && !loadingRef.current && !busyRef.current && sessionRef.current?.status === "active") {
        void mutate("heartbeat");
      }
    }, 20_000);
    const clock = window.setInterval(() => {
      const current = sessionRef.current;
      if (!current || current.status !== "active" || document.visibilityState !== "visible") return;
      const ageAtReceipt = Math.max(0, (Date.parse(current.as_of) - Date.parse(current.updated_at)) / 1000);
      const leaseRemaining = Math.max(0, current.idle_timeout_seconds - ageAtReceipt);
      const localElapsed = Math.max(0, (performance.now() - receivedAt.current) / 1000);
      setElapsedSeconds(Math.min(8 * 3600, current.active_seconds + Math.floor(Math.min(leaseRemaining, localElapsed))));
      if (localElapsed >= leaseRemaining + 1 && !busyRef.current && !loadingRef.current) void refresh();
    }, 1000);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", pauseWhenLeaving);
      window.removeEventListener("focus", onFocus);
      window.clearInterval(heartbeat);
      window.clearInterval(clock);
    };
  }, [mutate, refresh, workspacePath]);

  return (
    <StudySessionContext.Provider value={{
      session: workspacePath && !loading ? session : null,
      elapsedSeconds: workspacePath && !loading ? elapsedSeconds : 0,
      ownerId: workspacePath ? ownerId : null,
      accountScope: workspacePath ? accountScope : null,
      eligible: workspacePath && eligible,
      loading: workspacePath && loading,
      busy,
      error: workspacePath ? error : "",
      startBlocked,
      requiresAction,
      historyRevision,
      refresh,
      action: (action) => mutate(action),
      clear,
    }}>
      {children}
    </StudySessionContext.Provider>
  );
}

export function useStudySession() {
  const context = useContext(StudySessionContext);
  if (!context) throw new Error("Study session provider is missing");
  return context;
}
