import type { Attempt } from "./lesson-types";

type AttemptHistoryProps = {
  attempts: Attempt[];
};

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Дата недоступна"
    : date.toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" });
}

const STATUS_LABELS: Record<string, string> = {
  saved: "Сохранена",
  pending: "В очереди",
  failed: "Не обработана",
};

/**
 * Attempt log. The server is the source of truth for what happened to an
 * attempt, so statuses are rendered as reported and never recomputed here.
 */
export default function AttemptHistory({ attempts }: AttemptHistoryProps) {
  return (
    <section aria-label="История попыток">
      <h3>История попыток</h3>
      {attempts.length === 0 ? (
        <p role="status">Попыток пока нет. Отправьте решение выше — оно сохранится здесь.</p>
      ) : (
        <ol>
          {attempts.map((attempt) => (
            <li key={attempt.id}>
              <strong>{STATUS_LABELS[attempt.status] ?? attempt.status}</strong>
              {" · "}
              <time dateTime={attempt.created_at}>{formatDate(attempt.created_at)}</time>
              {" · "}
              {attempt.result.message ?? "Попытка сохранена"}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
