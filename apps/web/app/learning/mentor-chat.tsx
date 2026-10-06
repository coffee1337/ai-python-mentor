"use client";
import { FormEvent, useEffect, useState } from "react";
import { api, errorMessage, newRequestId } from "../lib/api";
import RichText from "./rich-text";
type Message = {
  id: string;
  role: string;
  content: string;
  status: string;
  created_at: string;
};
type Pending = { request_id: string; message: string };
type MentorOverview = {
  status: "configured" | "unconfigured";
  purpose: string;
  examples: string[];
  message: string;
};
const QUESTIONS = [
  "Объясни тему проще, с бытовым примером",
  "Разбери пример кода по строкам",
  "Не понимаю, с чего начать задание",
];
export default function MentorChat({ lessonId }: { lessonId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [mentor, setMentor] = useState<MentorOverview | null>(null);
  const path = `/learning/lessons/${encodeURIComponent(lessonId)}/chat`;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setMessages([]);
    setMentor(null);
    setPending(null);
    setText("");
    Promise.allSettled([
      api<Message[]>(path, { signal: controller.signal }),
      api<{ mentor: MentorOverview }>("/learning/overview", {
        signal: controller.signal,
      }),
    ])
      .then(([history, overview]) => {
        if (controller.signal.aborted) return;
        if (history.status === "fulfilled") setMessages(history.value);
        else setError("Не удалось загрузить историю вопросов.");
        if (overview.status === "fulfilled") setMentor(overview.value.mentor);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path]);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      setMessages(await api<Message[]>(path));
    } catch {
      setError("Не удалось загрузить историю вопросов.");
    } finally {
      setLoading(false);
    }
  }

  async function send(payload: Pending) {
    if (busy || mentor?.status === "unconfigured") return;
    setBusy(true);
    setError("");
    setPending(payload);
    try {
      await api<Message>(path, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setPending(null);
      setText("");
      await refresh();
    } catch (reason) {
      setError(
        errorMessage(
          reason,
          "AI-наставник сейчас недоступен. Материал урока и проверка продолжают работать.",
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (text.trim())
      void send({ request_id: newRequestId(), message: text.trim() });
  }

  return (
    <section
      className="panel mentor-panel"
      aria-labelledby="mentor-title"
      aria-busy={busy}
    >
      <div className="mentor-heading">
        <span className="mentor-mark" aria-hidden="true">
          ✦
        </span>
        <div>
          <p className="page-kicker">Помощь по вашему вопросу</p>
          <h2 id="mentor-title">AI-наставник</h2>
        </div>
      </div>
      <p className="muted">
        {mentor?.purpose ||
          "Урок даёт основу. Нейросеть помогает объяснить её другими словами, разобрать непонятную строку и ваши ошибки."}
      </p>
      {mentor?.status === "unconfigured" && (
        <div className="mentor-unavailable" role="status">
          <strong>AI-наставник пока не подключён</strong>
          <p>{mentor.message}</p>
        </div>
      )}
      {loading && <p role="status">Загружаем историю…</p>}
      {!loading &&
        messages.length === 0 &&
        mentor?.status !== "unconfigured" && (
          <div className="mentor-empty">
            <strong>Что именно непонятно?</strong>
            <p>
              Можно выбрать вопрос ниже или описать затруднение своими словами.
            </p>
          </div>
        )}
      {messages.length > 0 && (
        <div
          className="mentor-messages"
          aria-live="polite"
          aria-label="История вопросов"
        >
          {messages.map((message) => (
            <article
              className={`mentor-message mentor-message-${message.role === "user" ? "user" : "assistant"}`}
              key={message.id}
            >
              <strong className="mentor-message-author">
                {message.role === "user" ? "Вы" : "Наставник"}
              </strong>
              <RichText text={message.content} />
              {message.status === "failed" && message.role === "user" && (
                <button
                  className="text-button"
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void send({
                      request_id: message.id,
                      message: message.content,
                    })
                  }
                >
                  Повторить ответ
                </button>
              )}
            </article>
          ))}
        </div>
      )}
      {error && (
        <div className="status-message" role="alert">
          <p>{error}</p>
          <p>
            Если AI не подключён или временно недоступен, вернитесь к объяснению
            и примеру в уроке.
          </p>
          {pending ? (
            <button
              className="button-secondary"
              type="button"
              disabled={busy}
              onClick={() => void send(pending)}
            >
              Повторить отправку
            </button>
          ) : (
            <button
              className="button-secondary"
              type="button"
              disabled={busy || loading}
              onClick={() => void refresh()}
            >
              Повторить загрузку
            </button>
          )}
        </div>
      )}
      {!pending && mentor?.status !== "unconfigured" && (
        <div className="mentor-suggestions" aria-label="Примеры вопросов">
          {QUESTIONS.map((question) => (
            <button
              className="mentor-suggestion"
              type="button"
              disabled={busy}
              key={question}
              onClick={() => {
                setText(question);
                document.getElementById("mentor-message")?.focus();
              }}
            >
              {question}
            </button>
          ))}
        </div>
      )}
      {busy && <p role="status">Ждём ответ наставника…</p>}
      {mentor?.status !== "unconfigured" && (
        <form className="mentor-form" onSubmit={submit}>
          <label htmlFor="mentor-message">Ваш вопрос по этому уроку</label>
          <textarea
            id="mentor-message"
            rows={4}
            maxLength={4000}
            placeholder="Например: зачем здесь кавычки?"
            required
            value={text}
            disabled={busy || !!pending}
            onChange={(event) => setText(event.target.value)}
          />
          <button
            className="button"
            type="submit"
            disabled={busy || loading || !!pending || !text.trim()}
          >
            {busy ? "Ожидаем ответ…" : "Спросить наставника"}
          </button>
          {pending && !busy && (
            <button
              className="button-secondary"
              type="button"
              onClick={() => setPending(null)}
            >
              Изменить вопрос
            </button>
          )}
        </form>
      )}
      <details className="mentor-note">
        <summary>Как учитывается помощь</summary>
        <p>
          Открытые уровни подсказок в задании учитываются как помощь. Переписка
          с наставником отдельно не снижает самостоятельность ответа.
        </p>
        <p>
          AI может ошибаться. Проверяйте объяснение по материалу урока и не
          отправляйте пароли или ключи.
        </p>
      </details>
    </section>
  );
}
