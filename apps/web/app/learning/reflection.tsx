"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage, newRequestId } from "../lib/api";

type Reflection = { id: string; lesson_id: string; exercise_version: string; text: string; feedback: string; created_at: string };
export default function ReflectionSection({ lessonId, version, userId }: { lessonId: string; version: string; userId: string }) {
  const [text, setText] = useState("");
  const [rows, setRows] = useState<Reflection[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const pending = useRef<{ key: string; text: string } | null>(null);
  const path = `/learning/lessons/${encodeURIComponent(lessonId)}/reflections`;
  const key = `mentor.lesson.draft.v2.${userId}.${lessonId}.${version}.reflection`;
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try { setRows(await api<Reflection[]>(path)); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  }, [path]);
  useEffect(() => {
    try { const draft = window.localStorage.getItem(key); if (draft !== null && draft.length <= 10000) setText(draft); } catch { /* Storage optional. */ }
    void load();
  }, [key, load]);
  function change(value: string) {
    setText(value);
    pending.current = null;
    try { window.localStorage.setItem(key, value); } catch { /* Storage optional. */ }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !text.trim()) return;
    setBusy(true);
    setError("");
    pending.current ??= { key: newRequestId(), text };
    try {
      const row = await api<Reflection>(path, { method: "POST", headers: { "Idempotency-Key": pending.current.key }, body: JSON.stringify({ text: pending.current.text }) });
      setRows((current) => [row, ...current.filter((item) => item.id !== row.id)].slice(0, 20));
      setFeedback(row.feedback);
      pending.current = null;
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return (
    <section className="lesson-subsection" aria-labelledby="reflection-heading">
      <h3 id="reflection-heading">Письменный разбор</h3>
      <p className="muted">Запишите своё объяснение задания из раздела «Практика». Сохранение разбора не является проверкой правильности и не заменяет проверку усвоения.</p>
      <form className="settings-form" onSubmit={submit}>
        <label htmlFor="reflection-text">Ваше объяснение</label>
        <textarea id="reflection-text" value={text} onChange={(event) => change(event.target.value)} required maxLength={10000} rows={6} disabled={busy} />
        <button className="form-button" disabled={busy || !text.trim()}>{busy ? "Сохраняем…" : "Сохранить разбор"}</button>
      </form>
      {feedback && <p role="status">{feedback}</p>}
      {error && <div role="alert"><p className="form-error">{error}</p><button className="text-button" disabled={loading || busy} onClick={() => void load()}>Обновить историю</button></div>}
      {loading && <p role="status">Загружаем историю разборов…</p>}
      {!loading && rows.length === 0 && !error && <p className="muted">Сохранённых разборов пока нет.</p>}
      {rows.length > 0 && <details><summary>Сохранённые разборы ({rows.length})</summary>{rows.map((row) => <article className="saved-item" key={row.id}><p className="preserve-lines">{row.text}</p><p className="muted">{row.feedback}</p><time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString("ru-RU")}</time></article>)}</details>}
    </section>
  );
}
