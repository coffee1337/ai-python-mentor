"use client";

import { FormEvent, useEffect, useState } from "react";
import { api } from "../lib/api";

type Message = { id: string; role: string; content: string; status: string; created_at: string };
type Pending = { request_id: string; message: string };

export default function MentorChat({ lessonId }: { lessonId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const path = `/learning/lessons/${lessonId}/chat`;

  useEffect(() => {
    const controller = new AbortController();
    api<Message[]>(path, { signal: controller.signal })
      .then(setMessages)
      .catch(() => { if (!controller.signal.aborted) setError("Не удалось загрузить историю."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [path]);

  async function refresh() {
    setLoading(true); setError("");
    try { setMessages(await api<Message[]>(path)); }
    catch { setError("Не удалось загрузить историю."); }
    finally { setLoading(false); }
  }

  async function send(payload: Pending) {
    if (busy) return;
    setBusy(true); setError(""); setPending(payload);
    try {
      await api<Message>(path, { method: "POST", body: JSON.stringify(payload) });
      setPending(null); setText("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Наставник временно недоступен.");
    } finally { setBusy(false); }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (text.trim()) void send({ request_id: crypto.randomUUID(), message: text.trim() });
  }

  return <section aria-label="Чат с наставником">
    <h3>Наставник по этому уроку</h3>
    <p className="muted">Небольшие подсказки, не готовые решения. Использование помощи учитывается при завершении урока. Ответ AI может быть ошибочным; не отправляйте секреты.</p>
    {loading && <p role="status">Загружаем историю…</p>}
    <div aria-live="polite">{messages.map(message => <div key={message.id}>
      <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}><strong>{message.role === "user" ? "Вы" : "Наставник"}: </strong>{message.content}</p>
      {message.status === "failed" && <button disabled={busy} onClick={() => void send({ request_id: message.id, message: message.content })}>Повторить ответ</button>}
    </div>)}</div>
    {error && <div role="alert"><p>{error}</p>
      {pending ? <button disabled={busy} onClick={() => void send(pending)}>Повторить отправку</button>
        : <button disabled={busy || loading} onClick={() => void refresh()}>Повторить загрузку</button>}
    </div>}
    {busy && <p role="status">Наставник готовит подсказку…</p>}
    <form onSubmit={submit}>
      <label htmlFor="mentor-message">Ваш вопрос</label>
      <textarea id="mentor-message" maxLength={4000} required value={text} disabled={busy || !!pending}
        onChange={event => setText(event.target.value)} />
      <button type="submit" disabled={busy || loading || !!pending || !text.trim()}>Спросить</button>
      {pending && !busy && <button type="button" onClick={() => setPending(null)}>Изменить вопрос</button>}
    </form>
  </section>;
}
