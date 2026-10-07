"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, newRequestId } from "../lib/api";
import RichText from "./rich-text";
import DraftSyncStatus from "../components/draft-sync-status";
import { publicDraftVersion, useSyncedDraft } from "../lib/use-synced-draft";
type ReflectionDraft = { text: string };
type Reflection = {
  id: string;
  lesson_id: string;
  exercise_version: string;
  text: string;
  feedback: string;
  created_at: string;
};
export default function ReflectionSection({
  lessonId,
  version,
  userId,
}: {
  lessonId: string;
  version: string;
  userId: string;
}) {
  const [text, setText] = useState("");
  const [rows, setRows] = useState<Reflection[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [draftReadyKey, setDraftReadyKey] = useState<string | null>(null);
  const [hasLocalDraft, setHasLocalDraft] = useState(false);
  const pending = useRef<{ key: string; text: string } | null>(null);
  const generation = useRef(0);
  const historyRequest = useRef(0);
  const path = `/learning/lessons/${encodeURIComponent(lessonId)}/reflections`;
  const key = `mentor.lesson.draft.v2.${userId}.${lessonId}.${version}.reflection`;
  const publicVersion = publicDraftVersion(version);
  const sync = useSyncedDraft<ReflectionDraft>({
    userId, localKey: key, ready: draftReadyKey === key,
    identity: publicVersion ? { kind: "reflection", resource_id: lessonId, version: publicVersion, milestone_id: "" } : null,
    current: { text }, empty: { text: "" }, hasLocalDraft,
    validate: (value) => {
      const candidate = value as Partial<ReflectionDraft> | null;
      return candidate && typeof candidate.text === "string" && candidate.text.length <= 10000 ? { text: candidate.text } : null;
    },
    onApply: (value) => {
      const next = value?.text ?? "";
      setText(next);
      setHasLocalDraft(!!next);
      pending.current = null;
      try {
        if (next) window.localStorage.setItem(key, next);
        else window.localStorage.removeItem(key);
      } catch { /* Keep the restored text editable even when cache storage fails. */ }
    },
  });
  const accountChanged = sync.phase === "account_changed";
  const load = useCallback(async (signal?: AbortSignal) => {
    const request = ++historyRequest.current;
    setLoading(true);
    setError("");
    try {
      const next = await api<Reflection[]>(path, { signal });
      if (!signal?.aborted && request === historyRequest.current) setRows(next);
    } catch (reason) {
      if (!signal?.aborted && request === historyRequest.current) setError(errorMessage(reason));
    } finally {
      if (!signal?.aborted && request === historyRequest.current) setLoading(false);
    }
  }, [path, userId]);
  useEffect(() => {
    ++generation.current;
    const controller = new AbortController();
    pending.current = null;
    setRows([]);
    setFeedback("");
    setBusy(false);
    setDraftReadyKey(null);
    setText("");
    setHasLocalDraft(false);
    try {
      const draft = window.localStorage.getItem(key);
      if (draft !== null && draft.length <= 10000) {
        setText(draft);
        setHasLocalDraft(!!draft);
      }
    } catch {
      /* Storage optional. */
    }
    setDraftReadyKey(key);
    void load(controller.signal);
    return () => {
      ++generation.current;
      ++historyRequest.current;
      controller.abort();
    };
  }, [key, load]);
  function change(value: string) {
    if (sync.isAccountInvalid()) return;
    setText(value);
    setHasLocalDraft(!!value);
    sync.changed({ text: value });
    pending.current = null;
    try {
      window.localStorage.setItem(key, value);
    } catch {
      /* Storage optional. */
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || sync.isAccountInvalid() || !sync.guardHeaders || draftReadyKey !== key || !text.trim()) return;
    setBusy(true);
    const currentGeneration = generation.current;
    setError("");
    pending.current ??= { key: newRequestId(), text };
    try {
      const row = await api<Reflection>(path, {
        method: "POST",
        headers: { ...sync.guardHeaders, "Idempotency-Key": pending.current.key },
        body: JSON.stringify({ text: pending.current.text }),
      });
      if (currentGeneration !== generation.current) return;
      setRows((current) =>
        [row, ...current.filter((item) => item.id !== row.id)].slice(0, 20),
      );
      setFeedback(row.feedback);
      pending.current = null;
    } catch (reason) {
      if (currentGeneration === generation.current && sync.handleAccountError(reason)) return;
      if (currentGeneration === generation.current) setError(errorMessage(reason));
    } finally {
      if (currentGeneration === generation.current) setBusy(false);
    }
  }
  return (
    <section className="lesson-subsection" aria-labelledby="reflection-heading">
      <h3 id="reflection-heading">Объясните своими словами</h3>
      <p className="muted">
        Что делает пример? Почему вы выбрали такое решение? Запишите 2–3
        предложения. Это ваш сохранённый разбор, он не заменяет проверку
        понимания.
      </p>
      <form className="settings-form" onSubmit={submit}>
        <label htmlFor="reflection-text">Ваше объяснение</label>
        <textarea
          id="reflection-text"
          placeholder="Я понял(а), что… Остался вопрос о…"
          value={text}
          onChange={(event) => change(event.target.value)}
          required
          maxLength={10000}
          rows={6}
          disabled={busy || accountChanged || draftReadyKey !== key}
        />
        <DraftSyncStatus sync={sync} preview={(value) => value.text || "Пустое объяснение."} disabled={busy || accountChanged} />
        <button className="button" disabled={busy || accountChanged || !sync.guardHeaders || draftReadyKey !== key || !text.trim()}>
          {busy ? "Сохраняем…" : "Сохранить разбор"}
        </button>
      </form>
      {feedback && <p role="status">{feedback}</p>}
      {error && (
        <div role="alert">
          <p className="form-error">{error}</p>
          <button
            className="text-button"
            disabled={loading || busy || accountChanged}
            onClick={() => void load()}
          >
            Обновить историю
          </button>
        </div>
      )}
      {loading && <p role="status">Загружаем историю разборов…</p>}
      {!loading && rows.length === 0 && !error && (
        <p className="muted">Сохранённых разборов пока нет.</p>
      )}
      {rows.length > 0 && (
        <details className="lesson-detail">
          <summary>Сохранённые разборы ({rows.length})</summary>
          {rows.map((row) => (
            <article className="saved-item" key={row.id}>
              <RichText text={row.text} />
              <p className="muted">{row.feedback}</p>
              <time dateTime={row.created_at}>
                {new Date(row.created_at).toLocaleString("ru-RU")}
              </time>
            </article>
          ))}
        </details>
      )}
    </section>
  );
}
