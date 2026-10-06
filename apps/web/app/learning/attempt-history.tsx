"use client";

import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../lib/api";
import type { Attempt } from "./lesson-types";

export type AttemptSource = {
  attempt_id: string;
  exercise_id: string;
  exercise_version: number | null;
  source_code: string;
  language: string;
  mode: string;
  created_at: string;
  version_verified: boolean;
};
type RestoreTarget = {
  exercise_id: string;
  version: number;
  language: string;
  mode: string;
  maxSourceLength: number;
};
type AttemptHistoryProps = {
  attempts: Attempt[];
  restoreTarget?: RestoreTarget;
  currentSource?: string;
  restoreDisabled?: boolean;
  onRestore?: (attempt: AttemptSource) => boolean;
};
type SourcePreview = {
  attemptId: string;
  loading: boolean;
  error: string;
  data: AttemptSource | null;
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
export default function AttemptHistory({
  attempts,
  restoreTarget,
  currentSource,
  restoreDisabled = false,
  onRestore,
}: AttemptHistoryProps) {
  const [preview, setPreview] = useState<SourcePreview | null>(null);
  const [confirmRestore, setConfirmRestore] = useState(false);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => request.current?.abort(), []);

  async function showSource(attemptId: string) {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setConfirmRestore(false);
    setPreview({ attemptId, loading: true, error: "", data: null });
    try {
      const data = await api<AttemptSource>(
        `/learning/attempts/${encodeURIComponent(attemptId)}/source`,
        { signal: controller.signal, cache: "no-store" },
      );
      if (controller.signal.aborted) return;
      if (data.attempt_id !== attemptId)
        throw new Error("Source does not match the requested attempt");
      setPreview({ attemptId, loading: false, error: "", data });
    } catch (reason) {
      if (!controller.signal.aborted)
        setPreview({
          attemptId,
          loading: false,
          error: errorMessage(reason, "Не удалось загрузить код. Попробуйте снова."),
          data: null,
        });
    }
  }

  function hideSource() {
    request.current?.abort();
    setConfirmRestore(false);
    setPreview(null);
  }

  function restoreRestriction(data: AttemptSource): string | null {
    if (!data.version_verified || data.exercise_version === null)
      return "Версию этой попытки подтвердить не удалось. Код доступен для просмотра.";
    if (!restoreTarget || !onRestore) return "Код доступен для просмотра.";
    if (data.exercise_id !== restoreTarget.exercise_id)
      return "Это код другого задания. Восстановление в текущий редактор недоступно.";
    if (data.exercise_version !== restoreTarget.version)
      return `Сейчас открыта версия ${restoreTarget.version}. Код другой версии доступен для просмотра.`;
    if (data.language !== restoreTarget.language || data.mode !== restoreTarget.mode)
      return "Формат этой попытки отличается от текущего задания. Код доступен для просмотра.";
    if (data.source_code.length > restoreTarget.maxSourceLength)
      return "Этот код превышает лимит редактора. Он доступен для просмотра полностью.";
    return null;
  }

  function restore(data: AttemptSource) {
    if (restoreDisabled || restoreRestriction(data)) return;
    if (onRestore?.(data)) setConfirmRestore(false);
  }

  return (
    <section aria-label="История попыток">
      <h3>История попыток</h3>
      {attempts.length === 0 ? (
        <p role="status">
          Попыток пока нет. Отправьте решение выше — оно сохранится здесь.
        </p>
      ) : (
        <ol>
          {attempts.map((attempt) => (
            <li key={attempt.id}>
              <strong>{STATUS_LABELS[attempt.status] ?? attempt.status}</strong>
              {" · "}
              <time dateTime={attempt.created_at}>
                {formatDate(attempt.created_at)}
              </time>
              {" · "}
              {attempt.result.message ?? "Попытка сохранена"}
              {typeof attempt.result.tests_total === "number" &&
                attempt.result.tests_total > 0 && (
                  <p>
                    Тесты: {attempt.result.tests_passed} из{" "}
                    {attempt.result.tests_total}.
                  </p>
                )}
              <div className="attempt-source-actions">
                <button
                  className="text-button"
                  type="button"
                  aria-expanded={preview?.attemptId === attempt.id}
                  aria-controls={`attempt-source-${attempt.id}`}
                  onClick={() =>
                    preview?.attemptId === attempt.id
                      ? hideSource()
                      : void showSource(attempt.id)
                  }
                >
                  {preview?.attemptId === attempt.id ? "Скрыть код" : "Посмотреть код"}
                </button>
              </div>
              {preview?.attemptId === attempt.id && (
                <div
                  id={`attempt-source-${attempt.id}`}
                  className="review-result"
                  aria-busy={preview.loading}
                >
                  {preview.loading && <p role="status">Загружаем сохранённый код…</p>}
                  {preview.error && (
                    <div role="alert">
                      <p className="form-error">{preview.error}</p>
                      <button
                        className="text-button"
                        type="button"
                        onClick={() => void showSource(attempt.id)}
                      >
                        Повторить загрузку кода
                      </button>
                    </div>
                  )}
                  {preview.data && (
                    <>
                      <p>
                        {preview.data.version_verified && preview.data.exercise_version !== null
                          ? `Версия задания: ${preview.data.exercise_version}.`
                          : "Версия задания не подтверждена."}{" "}
                        Сохранено {formatDate(preview.data.created_at)}.
                      </p>
                      <pre
                        className="attempt-source-preview"
                        tabIndex={0}
                        aria-label="Сохранённый код попытки"
                      >
                        <code>{preview.data.source_code}</code>
                      </pre>
                      {restoreRestriction(preview.data) ? (
                        <p className="muted">{restoreRestriction(preview.data)}</p>
                      ) : (
                        <>
                          {restoreDisabled && (
                            <p className="muted">
                              Восстановление станет доступно после завершения текущей отправки.
                            </p>
                          )}
                          {confirmRestore ? (
                            <div className="review-result" role="group" aria-label="Замена кода в редакторе">
                              <p>
                                Заменить код в редакторе этой попыткой? Предыдущий черновик
                                сохранится в этом браузере и останется доступен под
                                редактором при повторном открытии урока. Выход из аккаунта
                                удаляет локальные черновики.
                              </p>
                              <div className="attempt-source-actions">
                                <button
                                  className="text-button"
                                  type="button"
                                  disabled={restoreDisabled}
                                  onClick={() => restore(preview.data!)}
                                >
                                  Заменить код
                                </button>
                                <button
                                  className="text-button"
                                  type="button"
                                  onClick={() => setConfirmRestore(false)}
                                >
                                  Отмена
                                </button>
                              </div>
                            </div>
                          ) : (
                            <button
                              className="text-button"
                              type="button"
                              disabled={restoreDisabled}
                              onClick={() => {
                                if (currentSource !== preview.data!.source_code)
                                  setConfirmRestore(true);
                                else restore(preview.data!);
                              }}
                            >
                              Восстановить в редактор
                            </button>
                          )}
                        </>
                      )}
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
