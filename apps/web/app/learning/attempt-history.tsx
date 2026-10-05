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
  failed: "Тесты не пройдены",
  unavailable: "Сохранена без исполнения",
  passed: "Тесты пройдены",
  timeout: "Превышено время",
  resource_violation: "Превышен лимит ресурсов",
  runner_error: "Ошибка обработки",
  queued: "В очереди",
  running: "Выполняется",
  cancelled: "Отменена",
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
              {typeof attempt.result.tests_total === "number" && attempt.result.tests_total > 0 && <p>Тесты: {attempt.result.tests_passed} из {attempt.result.tests_total}.</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
