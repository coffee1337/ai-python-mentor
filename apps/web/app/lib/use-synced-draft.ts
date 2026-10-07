"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, errorMessage } from "./api";

export type DraftIdentity = {
  kind: "lesson_flow" | "coding" | "reflection" | "project_milestone";
  resource_id: string;
  version: number;
  milestone_id: string;
};
type DraftEnvelope<T> = {
  identity: DraftIdentity;
  revision: number;
  content: T | null;
  updated_at: string | null;
};
export type DraftSyncPhase = "loading" | "empty" | "saved" | "local" | "saving" | "error" | "conflict" | "account_changed";
export type SyncedDraft<T> = {
  phase: DraftSyncPhase;
  message: string;
  conflict: DraftEnvelope<T> | null;
  backup: { content: T | null } | null;
  current: T;
  enabled: boolean;
  changed: (content: T) => void;
  clear: () => void;
  retry: () => void;
  useAccount: () => void;
  keepMine: () => void;
  restoreBackup: () => void;
  preserve: (content?: T | null) => boolean;
  isAccountInvalid: () => boolean;
  guardHeaders: Record<string, string> | null;
  handleAccountError: (reason: unknown) => boolean;
};

function fingerprint(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(fingerprint).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${fingerprint((value as Record<string, unknown>)[key])}`).join(",")}}`;
}

export function publicDraftVersion(value: string | number | null | undefined): number | null {
  if (typeof value === "string" && !/^[1-9]\d*$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

// The caller owns the editor and its browser cache. Only explicit edits enter
// the save queue; applying a GET response never creates a write by itself.
export function useSyncedDraft<T>({
  userId, identity, localKey, ready, current, hasLocalDraft, empty, validate, onApply,
}: {
  userId: string;
  identity: DraftIdentity | null;
  localKey: string;
  ready: boolean;
  current: T;
  hasLocalDraft: boolean;
  empty: T;
  validate: (value: unknown) => T | null;
  onApply: (value: T | null) => void;
}): SyncedDraft<T> {
  const scope = ready && identity ? `${userId}:${fingerprint(identity)}:${localKey}` : "";
  const options = useRef({ userId, identity, localKey, current, hasLocalDraft, empty, validate, onApply });
  options.current = { userId, identity, localKey, current, hasLocalDraft, empty, validate, onApply };
  const [phase, setPhase] = useState<DraftSyncPhase>("loading");
  const [message, setMessage] = useState("");
  const [conflict, setConflict] = useState<DraftEnvelope<T> | null>(null);
  const [backup, setBackup] = useState<{ content: T | null } | null>(null);
  const [authPaused, setAuthPaused] = useState(false);
  const [, revealAccountBinding] = useState(0);
  const generation = useRef(0);
  const activeScope = useRef("");
  const revision = useRef(0);
  const acknowledged = useRef<{ revision: number; fingerprint: string } | null>(null);
  const accountBinding = useRef<{ ownerId: string; scope: string } | null>(null);
  const invalidatedOwner = useRef<string | null>(null);
  const desired = useRef<T | null>(current);
  const dirty = useRef(false);
  const initialized = useRef(false);
  const blocked = useRef(false);
  const conflictRef = useRef<DraftEnvelope<T> | null>(null);
  const saving = useRef(false);
  const reading = useRef(false);
  const controllers = useRef(new Set<AbortController>());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runSave = useRef<() => Promise<void>>(async () => {});
  const runRead = useRef<(force?: boolean) => Promise<void>>(async () => {});
  const cancelTimer = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const queue = useCallback(() => {
    cancelTimer();
    if (!activeScope.current || !initialized.current || blocked.current || conflictRef.current || !dirty.current) return;
    timer.current = setTimeout(() => { void runSave.current(); }, 750);
  }, [cancelTimer]);

  function stopForAccountChange(notifyWorkspace = true) {
    if (invalidatedOwner.current === options.current.userId) return;
    invalidatedOwner.current = options.current.userId;
    ++generation.current;
    activeScope.current = "";
    accountBinding.current = null;
    blocked.current = true;
    cancelTimer();
    for (const controller of controllers.current) controller.abort();
    controllers.current.clear();
    conflictRef.current = null;
    setAuthPaused(true);
    setConflict(null);
    setBackup(null);
    setPhase("account_changed");
    setMessage("Аккаунт в браузере изменился. Синхронизация остановлена; текст не отправлен в другой аккаунт. Обновите страницу и продолжите в нужном аккаунте.");
    if (notifyWorkspace) window.dispatchEvent(new CustomEvent("mentor:workspace-account-invalid"));
  }

  function checkedEnvelope(value: DraftEnvelope<unknown>): DraftEnvelope<T> {
    const expected = options.current.identity;
    if (!expected || fingerprint(value.identity) !== fingerprint(expected) ||
      !Number.isSafeInteger(value.revision) || value.revision < 0) throw new Error("Invalid draft response");
    const content = value.content === null ? null : options.current.validate(value.content);
    if (value.content !== null && content === null) throw new Error("Invalid draft content");
    return { ...value, content };
  }

  function acknowledge(remote: DraftEnvelope<T>) {
    acknowledged.current = { revision: remote.revision, fingerprint: fingerprint(remote.content) };
    try {
      window.localStorage.setItem(`${options.current.localKey}.sync-meta`, JSON.stringify(acknowledged.current));
    } catch { /* Unknown caches will require a choice rather than being overwritten. */ }
  }

  runRead.current = async (force = false) => {
    const mine = generation.current;
    if (!activeScope.current || reading.current || saving.current || (!force && dirty.current && initialized.current)) return;
    const first = !initialized.current;
    const controller = new AbortController();
    controllers.current.add(controller);
    reading.current = true;
    if (first) setPhase("loading");
    const snapshot = options.current;
    try {
      if (!accountBinding.current || accountBinding.current.ownerId !== snapshot.userId) {
        const owner = await api<{ id: string; account_scope: string }>("/me", { signal: controller.signal, cache: "no-store" });
        if (mine !== generation.current || controller.signal.aborted) return;
        if (owner.id !== snapshot.userId) {
          stopForAccountChange();
          return;
        }
        if (typeof owner.account_scope !== "string" || !owner.account_scope) throw new Error("Missing account scope");
        accountBinding.current = { ownerId: owner.id, scope: owner.account_scope };
        revealAccountBinding((value) => value + 1);
      }
      const params = new URLSearchParams({ ...snapshot.identity!, version: String(snapshot.identity!.version) });
      const remote = checkedEnvelope(await api<DraftEnvelope<unknown>>(`/learning/drafts?${params}`, {
        signal: controller.signal, cache: "no-store", headers: { "X-Account-Scope": accountBinding.current.scope },
      }));
      if (mine !== generation.current || controller.signal.aborted) return;
      revision.current = remote.revision;
      initialized.current = true;
      blocked.current = false;
      const local = dirty.current ? desired.current : options.current.current;
      const different = fingerprint(remote.content) !== fingerprint(local) &&
        !(remote.content === null && fingerprint(local) === fingerprint(options.current.empty));
      const ownsLocal = dirty.current || options.current.hasLocalDraft ||
        fingerprint(local) !== fingerprint(options.current.empty);
      const lastAck = acknowledged.current;
      const unchangedCache = !dirty.current && lastAck !== null &&
        lastAck.fingerprint === fingerprint(local) && remote.revision >= lastAck.revision;
      const unchangedAccount = lastAck !== null && remote.revision === lastAck.revision &&
        lastAck.fingerprint === fingerprint(remote.content);
      if (dirty.current && unchangedAccount) {
        conflictRef.current = null;
        setConflict(null);
        setPhase("local");
        queue();
        return;
      }
      if (remote.content === null && remote.revision > 0 && unchangedCache) {
        options.current.onApply(null);
        desired.current = null;
        dirty.current = false;
        conflictRef.current = null;
        setConflict(null);
        acknowledge(remote);
        setPhase("empty");
        setMessage("Черновик очищен в аккаунте. Сохранённый ранее вариант убран с этого устройства.");
        return;
      }
      if (remote.content !== null && unchangedCache) {
        if (different) options.current.onApply(remote.content);
        desired.current = remote.content;
        dirty.current = false;
        conflictRef.current = null;
        setConflict(null);
        acknowledge(remote);
        setPhase("saved");
        setMessage(different ? "Черновик обновлён из аккаунта. Изменений на этом устройстве не было." : "");
        return;
      }
      // An absent row can receive a local draft. A tombstone cannot silently
      // resurrect an old cache from another device or an earlier lesson step.
      if (different && ownsLocal && (remote.content !== null || remote.revision > 0)) {
        conflictRef.current = remote;
        setConflict(remote);
        setPhase("conflict");
        setMessage("");
        return;
      }
      conflictRef.current = null;
      setConflict(null);
      if (remote.content !== null && !ownsLocal) {
        options.current.onApply(remote.content);
        desired.current = remote.content;
        dirty.current = false;
        acknowledge(remote);
        setPhase("saved");
        setMessage("Восстановлен черновик из аккаунта.");
      } else if (different && ownsLocal && remote.revision === 0) {
        desired.current = local;
        dirty.current = true;
        setPhase("local");
        setMessage("");
        queue();
      } else {
        desired.current = remote.content;
        dirty.current = false;
        acknowledge(remote);
        setPhase(remote.content === null ? "empty" : "saved");
        setMessage("");
      }
    } catch (reason) {
      if (mine !== generation.current || controller.signal.aborted) return;
      if (reason instanceof ApiError && (reason.code === "account_changed" || reason.status === 401)) {
        stopForAccountChange();
        return;
      }
      blocked.current = true;
      setPhase("error");
      setMessage(`${errorMessage(reason, "Не удалось загрузить черновик из аккаунта.")} Ваш текст остаётся в редакторе.`);
    } finally {
      controllers.current.delete(controller);
      if (mine === generation.current) reading.current = false;
    }
  };

  runSave.current = async () => {
    cancelTimer();
    if (!activeScope.current || !initialized.current || !accountBinding.current || accountBinding.current.ownerId !== options.current.userId || blocked.current || conflictRef.current || saving.current || reading.current || !dirty.current) return;
    const mine = generation.current;
    const content = desired.current;
    const sent = fingerprint(content);
    const controller = new AbortController();
    controllers.current.add(controller);
    saving.current = true;
    setPhase("saving");
    setMessage("");
    let needsConflictRead = false;
    try {
      const remote = checkedEnvelope(await api<DraftEnvelope<unknown>>("/learning/drafts", {
        method: "POST", signal: controller.signal, headers: { "X-Account-Scope": accountBinding.current.scope },
        body: JSON.stringify({ identity: options.current.identity, expected_revision: revision.current, content }),
      }));
      if (mine !== generation.current || controller.signal.aborted) return;
      revision.current = remote.revision;
      acknowledge(remote);
      if (sent === fingerprint(desired.current)) {
        dirty.current = false;
        setPhase(content === null ? "empty" : "saved");
      } else {
        setPhase("local");
      }
    } catch (reason) {
      if (mine !== generation.current || controller.signal.aborted) return;
      if (reason instanceof ApiError && (reason.code === "account_changed" || reason.status === 401)) {
        stopForAccountChange();
        return;
      }
      blocked.current = true;
      if (reason instanceof ApiError && reason.status === 409 && reason.code === "draft_conflict") {
        needsConflictRead = true;
        setPhase("loading");
      } else {
        setPhase("error");
        setMessage(`${errorMessage(reason)} Ваш текст остаётся в редакторе; можно повторить синхронизацию.`);
      }
    } finally {
      controllers.current.delete(controller);
      if (mine === generation.current) {
        saving.current = false;
        if (needsConflictRead) void runRead.current(true);
        else if (dirty.current && !blocked.current) {
          if (desired.current === null) void runSave.current();
          else queue();
        }
      }
    }
  };

  useEffect(() => {
    ++generation.current;
    activeScope.current = scope;
    initialized.current = false;
    blocked.current = false;
    dirty.current = false;
    desired.current = options.current.current;
    conflictRef.current = null;
    saving.current = false;
    reading.current = false;
    revision.current = 0;
    setConflict(null);
    setMessage("");
    setBackup(null);
    setAuthPaused(false);
    acknowledged.current = null;
    accountBinding.current = null;
    setPhase("loading");
    if (invalidatedOwner.current === options.current.userId) {
      activeScope.current = "";
      blocked.current = true;
      setAuthPaused(true);
      setPhase("account_changed");
      setMessage("Аккаунт в браузере изменился. Синхронизация остановлена; текст не отправлен в другой аккаунт. Обновите страницу и продолжите в нужном аккаунте.");
    } else if (scope) {
      invalidatedOwner.current = null;
      try {
        const metadata = window.localStorage.getItem(`${options.current.localKey}.sync-meta`);
        if (metadata) {
          const stored = JSON.parse(metadata);
          if (Number.isSafeInteger(stored.revision) && stored.revision >= 0 && typeof stored.fingerprint === "string" && stored.fingerprint.length <= 180000) {
            acknowledged.current = stored;
          }
        }
        const raw = window.localStorage.getItem(`${options.current.localKey}.sync-backup`);
        if (raw) {
          const stored = JSON.parse(raw);
          const content = stored.content === null ? null : options.current.validate(stored.content);
          if (stored.content === null || content !== null) setBackup({ content });
        }
      } catch { /* A failed cache read must not erase the editor. */ }
      void runRead.current();
    }
    const refresh = () => { if (!dirty.current && !conflictRef.current && !blocked.current) void runRead.current(); };
    const storage = (event: StorageEvent) => {
      if (event.key === options.current.localKey) void runRead.current(true);
    };
    const authChanged = () => stopForAccountChange(false);
    window.addEventListener("focus", refresh);
    window.addEventListener("storage", storage);
    window.addEventListener("mentor:auth-changed", authChanged);
    return () => {
      ++generation.current;
      activeScope.current = "";
      cancelTimer();
      for (const controller of controllers.current) controller.abort();
      controllers.current.clear();
      window.removeEventListener("focus", refresh);
      window.removeEventListener("storage", storage);
      window.removeEventListener("mentor:auth-changed", authChanged);
    };
  }, [scope, cancelTimer]);

  function changed(content: T) {
    if (!scope || activeScope.current !== scope) return;
    desired.current = content;
    dirty.current = true;
    setMessage("");
    if (!conflictRef.current && !blocked.current) setPhase(initialized.current ? "local" : "loading");
    queue();
  }

  function preserve(content: T | null = options.current.current): boolean {
    if (invalidatedOwner.current === options.current.userId) return false;
    try {
      window.localStorage.setItem(`${options.current.localKey}.sync-backup`, JSON.stringify({ content }));
      setBackup({ content });
      return true;
    } catch {
      setMessage("Замена отменена: не удалось сохранить резервную копию на устройстве. Текст остался в редакторе. Скопируйте его в файл и освободите место в хранилище браузера.");
      return false;
    }
  }

  function useAccount() {
    const remote = conflictRef.current;
    if (!remote || !preserve()) return;
    cancelTimer();
    options.current.onApply(remote.content);
    desired.current = remote.content;
    dirty.current = false;
    revision.current = remote.revision;
    acknowledge(remote);
    conflictRef.current = null;
    setConflict(null);
    blocked.current = false;
    setPhase(remote.content === null ? "empty" : "saved");
    setMessage("Выбран вариант из аккаунта. Предыдущий текст сохранён ниже.");
  }

  function keepMine() {
    const remote = conflictRef.current;
    if (!remote || !preserve(remote.content)) return;
    revision.current = remote.revision;
    desired.current = dirty.current ? desired.current : options.current.current;
    dirty.current = true;
    conflictRef.current = null;
    setConflict(null);
    blocked.current = false;
    void runSave.current();
  }

  function restoreBackup() {
    if (!backup) return;
    const previous = backup.content;
    if (!preserve()) return;
    options.current.onApply(previous);
    desired.current = previous;
    dirty.current = true;
    if (!conflictRef.current && !blocked.current) setPhase("local");
    setMessage("Предыдущий вариант возвращён. Заменённый текст сохранён в резервной копии.");
    queue();
  }

  function clear() {
    if (!scope || activeScope.current !== scope) return;
    cancelTimer();
    options.current.onApply(null);
    desired.current = null;
    dirty.current = true;
    if (!conflictRef.current && !blocked.current) setPhase(initialized.current ? "local" : "loading");
    void runSave.current();
  }

  return {
    phase, message, conflict, backup, current, enabled: !!scope && (!authPaused || phase === "account_changed"),
    changed, clear, preserve, useAccount, keepMine, restoreBackup,
    isAccountInvalid: () => invalidatedOwner.current === options.current.userId,
    guardHeaders: accountBinding.current && accountBinding.current.ownerId === userId && invalidatedOwner.current !== userId
      ? { "X-Account-Scope": accountBinding.current.scope } : null,
    handleAccountError: (reason) => {
      if (activeScope.current !== scope || !(reason instanceof ApiError) || (reason.code !== "account_changed" && reason.status !== 401)) return false;
      stopForAccountChange();
      return true;
    },
    retry: () => {
      if (invalidatedOwner.current === options.current.userId || reading.current || saving.current) return;
      cancelTimer();
      accountBinding.current = null;
      void runRead.current(true);
    },
  };
}
