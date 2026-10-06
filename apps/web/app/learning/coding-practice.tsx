"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, errorMessage, newRequestId } from "../lib/api";
import RichText from "./rich-text";
import LessonPractice, { SOURCE_LIMIT } from "./lesson-practice";
import AttemptHistory from "./attempt-history";
import HintLadder from "./hint-ladder";
import type { Attempt } from "./lesson-types";
type CodingSpec = {
  exercise_id: string;
  lesson_id: string;
  version: number | string;
  prompt: string;
  starter_code: string;
  function_name: string;
  public_examples: {
    args: unknown[];
    kwargs: Record<string, unknown>;
    expected: unknown;
  }[];
};
type Capabilities = {
  configured: boolean;
  message: string;
  async_jobs: boolean;
};
type Job = {
  id: string;
  attempt_id: string;
  exercise_id: string;
  status: string;
  result: Attempt["result"] | null;
};
type Submission = { key: string; source: string };
const ACTIVE = new Set(["queued", "running"]);
const LABELS: Record<string, string> = {
  queued: "В очереди",
  running: "Выполняется",
  finished: "Обработка завершена",
  failed: "Обработка не удалась",
  cancelled: "Отменена",
  unavailable: "Исполнение недоступно",
};
function pythonValue(value: unknown): string {
  if (value === null) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (Array.isArray(value)) return `[${value.map(pythonValue).join(", ")}]`;
  if (typeof value === "object")
    return `{${Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${JSON.stringify(key)}: ${pythonValue(item)}`)
      .join(", ")}}`;
  return JSON.stringify(value) ?? String(value);
}
export default function CodingPractice({
  lessonId,
  userId,
}: {
  lessonId: string;
  userId: string;
}) {
  const [spec, setSpec] = useState<CodingSpec | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [source, setSource] = useState("");
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [pending, setPending] = useState<Submission | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [pollStopped, setPollStopped] = useState(false);
  const requestInFlight = useRef(false);
  const draftKey = spec
    ? `mentor.lesson.draft.v2.${userId}.${spec.exercise_id}.${spec.version}`
    : null;

  const history = useCallback(async (exerciseId: string) => {
    try {
      setAttempts(
        await api<Attempt[]>(
          `/learning/exercises/${encodeURIComponent(exerciseId)}/attempts`,
        ),
      );
      setHistoryError("");
    } catch (reason) {
      setHistoryError(errorMessage(reason));
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const nextSpec = await api<CodingSpec>(
        `/learning/exercises/${encodeURIComponent(lessonId)}/coding-specification`,
      );
      setSpec(nextSpec);
      const key = `mentor.lesson.draft.v2.${userId}.${nextSpec.exercise_id}.${nextSpec.version}`;
      let draft: string | null = null;
      try {
        draft = window.localStorage.getItem(key);
      } catch {
        /* Storage is optional. */
      }
      setSource(
        draft !== null && draft.length <= SOURCE_LIMIT
          ? draft
          : nextSpec.starter_code,
      );
      await history(nextSpec.exercise_id);
      try {
        setCapabilities(
          await api<Capabilities>("/learning/execution-capabilities"),
        );
      } catch {
        setCapabilities(null);
      }
    } catch (reason) {
      setError(
        reason instanceof ApiError && reason.status === 404
          ? "Для этого урока отдельное задание с кодом пока не опубликовано. Можно выполнить практику из материала и объяснить решение своими словами."
          : errorMessage(reason),
      );
    } finally {
      setLoading(false);
    }
  }, [history, lessonId, userId]);
  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!job || !ACTIVE.has(job.status) || pollStopped) return;
    const controller = new AbortController();
    const started = Date.now();
    const jobId = job.id;
    const timer = window.setInterval(async () => {
      if (requestInFlight.current) return;
      if (Date.now() - started > 90000) {
        setPollStopped(true);
        return;
      }
      requestInFlight.current = true;
      try {
        const next = await api<Job>(
          `/learning/jobs/${encodeURIComponent(jobId)}`,
          { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        setJob(next);
        setError("");
        if (!ACTIVE.has(next.status)) await history(next.exercise_id);
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(errorMessage(reason));
          setPollStopped(true);
        }
      } finally {
        requestInFlight.current = false;
      }
    }, 2000);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [job?.id, job?.status, pollStopped, history]);

  function changeSource(value: string) {
    setSource(value);
    if (draftKey)
      try {
        window.localStorage.setItem(draftKey, value);
      } catch {
        /* Storage is optional. */
      }
  }

  async function send(submission: Submission) {
    if (!spec || busy) return;
    setBusy(true);
    setError("");
    setPending(submission);
    try {
      const next = await api<Job>(
        `/learning/exercises/${encodeURIComponent(spec.exercise_id)}/jobs`,
        {
          method: "POST",
          headers: { "Idempotency-Key": submission.key },
          body: JSON.stringify({
            language: "python",
            mode: "function",
            source_code: submission.source,
          }),
        },
      );
      setPending(null);
      setJob(next);
      setPollStopped(false);
      await history(spec.exercise_id);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (source.trim()) void send(pending ?? { key: newRequestId(), source });
  }

  async function cancel() {
    if (!job || busy) return;
    setBusy(true);
    try {
      const next = await api<Job>(
        `/learning/jobs/${encodeURIComponent(job.id)}/cancel`,
        { method: "POST" },
      );
      setJob(next);
      await history(next.exercise_id);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="lesson-subsection"
      aria-labelledby="coding-task-heading"
      aria-busy={loading || busy}
    >
      <h3 id="coding-task-heading">Отдельное задание с кодом</h3>
      {loading && <p role="status">Загружаем условие…</p>}
      {spec && (
        <>
          <RichText text={spec.prompt} />
          <div className="coding-instructions">
            <strong>Что отправить</strong>
            <p>
              Дополните функцию <code>{spec.function_name}</code> в редакторе
              ниже. Сохраните её имя и параметры. Передайте результат через{" "}
              <code>return</code>, если условие не требует другого. Примеры
              показывают ожидаемое поведение.
            </p>
          </div>
          {spec.public_examples.length > 0 && (
            <div className="public-examples">
              <h4>Примеры входа и результата</h4>
              <p className="muted">
                Это условия проверки, а не результат запуска вашего кода.
              </p>
              <div className="public-example-list">
                {spec.public_examples.map((example, index) => (
                  <div className="public-example" key={index}>
                    <div>
                      <span>Вызов функции</span>
                      <code>
                        {spec.function_name}(
                        {[
                          ...example.args.map(pythonValue),
                          ...Object.entries(example.kwargs).map(
                            ([key, value]) => `${key}=${pythonValue(value)}`,
                          ),
                        ].join(", ")}
                        )
                      </code>
                    </div>
                    <div>
                      <span>Ожидаемый результат</span>
                      <code>{pythonValue(example.expected)}</code>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <HintLadder key={spec.exercise_id} lessonId={spec.exercise_id} />
          <LessonPractice
            source={source}
            onSourceChange={changeSource}
            onSubmit={submit}
            busy={busy}
            disabled={!!pending || (!!job && ACTIVE.has(job.status))}
            executionConfigured={capabilities?.configured ?? false}
          />
          {job && (
            <div className="review-result" role="status">
              <strong>{LABELS[job.status] ?? "Статус задания обновлён"}</strong>
              {job.result?.message && <p>{job.result.message}</p>}
              {typeof job.result?.tests_total === "number" &&
                job.result.tests_total > 0 && (
                  <p>
                    Тесты: {job.result.tests_passed} из {job.result.tests_total}
                    .
                  </p>
                )}
            </div>
          )}
          {job && ACTIVE.has(job.status) && (
            <button
              className="text-button"
              type="button"
              disabled={busy}
              onClick={() => void cancel()}
            >
              Отменить проверку
            </button>
          )}
          {pollStopped && job && ACTIVE.has(job.status) && (
            <p role="status">
              Автоматическое ожидание завершено.{" "}
              <button
                className="text-button"
                type="button"
                onClick={() => setPollStopped(false)}
              >
                Продолжить проверку статуса
              </button>
            </p>
          )}
          {historyError ? (
            <div role="alert">
              <p>{historyError}</p>
              <button
                className="text-button"
                onClick={() => void history(spec.exercise_id)}
              >
                Обновить историю
              </button>
            </div>
          ) : (
            <details className="lesson-detail">
              <summary>История попыток ({attempts.length})</summary>
              <AttemptHistory attempts={attempts} />
            </details>
          )}
        </>
      )}
      {error && (
        <div role="alert">
          <p className="form-error">{error}</p>
          {pending ? (
            <>
              <button
                className="text-button"
                disabled={busy}
                onClick={() => void send(pending)}
              >
                Повторить отправку
              </button>
              <button
                className="text-button"
                disabled={busy}
                onClick={() => setPending(null)}
              >
                Изменить решение
              </button>
            </>
          ) : (
            !spec && (
              <button
                className="text-button"
                disabled={loading}
                onClick={() => void load()}
              >
                Повторить загрузку
              </button>
            )
          )}
        </div>
      )}
    </section>
  );
}
