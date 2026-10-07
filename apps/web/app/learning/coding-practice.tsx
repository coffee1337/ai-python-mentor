"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, errorMessage, newRequestId } from "../lib/api";
import RichText from "./rich-text";
import LessonPractice, { SOURCE_LIMIT } from "./lesson-practice";
import AttemptHistory, { type AttemptSource } from "./attempt-history";
import HintLadder from "./hint-ladder";
import type { Attempt } from "./lesson-types";
import DraftSyncStatus from "../components/draft-sync-status";
import { useSyncedDraft } from "../lib/use-synced-draft";
type CodingSpec = {
  exercise_id: string;
  lesson_id: string;
  version: number;
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
type DraftBackup = { key: string; source: string };
type CodingDraft = { source_code: string; backup_source: string | null };
const CODE_LANGUAGE = "python";
const CODE_MODE = "function";
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
  const [historyLoading, setHistoryLoading] = useState(false);
  const [draftBackup, setDraftBackup] = useState<DraftBackup | null>(null);
  const [restoreMessage, setRestoreMessage] = useState("");
  const [restoreError, setRestoreError] = useState("");
  const [focusRequest, setFocusRequest] = useState(0);
  const [pollStopped, setPollStopped] = useState(false);
  const [hasLocalDraft, setHasLocalDraft] = useState(false);
  const requestInFlight = useRef(false);
  const historyRequest = useRef(0);
  const practiceRef = useRef<HTMLElement>(null);
  const draftKey = spec
    ? `mentor.lesson.draft.v2.${userId}.${spec.exercise_id}.${spec.version}`
    : null;
  const sync = useSyncedDraft<CodingDraft>({
    userId, localKey: draftKey ?? `mentor.lesson.draft.v2.${userId}.${lessonId}.pending`,
    ready: !loading && !!spec,
    identity: spec ? { kind: "coding", resource_id: spec.exercise_id, version: spec.version, milestone_id: "" } : null,
    current: { source_code: source, backup_source: draftBackup?.key === draftKey ? draftBackup.source : null },
    empty: { source_code: spec?.starter_code ?? "", backup_source: null }, hasLocalDraft,
    validate: (value) => {
      const candidate = value as Partial<CodingDraft> | null;
      if (!candidate || typeof candidate.source_code !== "string" || candidate.source_code.length > SOURCE_LIMIT ||
        !(candidate.backup_source === null || (typeof candidate.backup_source === "string" && candidate.backup_source.length <= SOURCE_LIMIT))) return null;
      return { source_code: candidate.source_code, backup_source: candidate.backup_source };
    },
    onApply: (value) => {
      const next = value?.source_code ?? spec?.starter_code ?? "";
      const backup = value?.backup_source ?? null;
      setSource(next);
      setDraftBackup(draftKey && backup !== null ? { key: draftKey, source: backup } : null);
      setHasLocalDraft(value !== null);
      setPending(null);
      if (draftKey) try {
        if (value) window.localStorage.setItem(draftKey, next);
        else window.localStorage.removeItem(draftKey);
        if (backup !== null) window.localStorage.setItem(`${draftKey}.backup`, backup);
        else window.localStorage.removeItem(`${draftKey}.backup`);
      } catch { /* Restored text remains in the editor when browser storage is unavailable. */ }
    },
  });
  const accountChanged = sync.phase === "account_changed";

  const history = useCallback(async (exerciseId: string, signal?: AbortSignal) => {
    const request = ++historyRequest.current;
    setHistoryLoading(true);
    try {
      const next = await api<Attempt[]>(
        `/learning/exercises/${encodeURIComponent(exerciseId)}/attempts`,
        { signal },
      );
      if (signal?.aborted || request !== historyRequest.current) return;
      setAttempts(next);
      setHistoryError("");
    } catch (reason) {
      if (!signal?.aborted && request === historyRequest.current)
        setHistoryError(errorMessage(reason));
    } finally {
      if (!signal?.aborted && request === historyRequest.current)
        setHistoryLoading(false);
    }
  }, []);

  const load = useCallback(async (signal?: AbortSignal) => {
    ++historyRequest.current;
    setLoading(true);
    setError("");
    setSpec(null);
    setAttempts([]);
    setJob(null);
    setPending(null);
    setCapabilities(null);
    setHistoryError("");
    setHistoryLoading(false);
    setDraftBackup(null);
    setRestoreMessage("");
    setRestoreError("");
    setFocusRequest(0);
    setHasLocalDraft(false);
    try {
      const nextSpec = await api<CodingSpec>(
        `/learning/exercises/${encodeURIComponent(lessonId)}/coding-specification`,
        { signal },
      );
      if (signal?.aborted) return;
      setSpec(nextSpec);
      const key = `mentor.lesson.draft.v2.${userId}.${nextSpec.exercise_id}.${nextSpec.version}`;
      let draft: string | null = null;
      let backup: string | null = null;
      try {
        draft = window.localStorage.getItem(key);
        backup = window.localStorage.getItem(`${key}.backup`);
        if (backup !== null && backup.length > SOURCE_LIMIT) {
          backup = null;
          window.localStorage.removeItem(`${key}.backup`);
        }
      } catch {
        /* Storage is optional. */
      }
      setDraftBackup(backup !== null ? { key, source: backup } : null);
      setHasLocalDraft(draft !== null && draft.length <= SOURCE_LIMIT || backup !== null);
      setSource(
        draft !== null && draft.length <= SOURCE_LIMIT
          ? draft
          : nextSpec.starter_code,
      );
      await history(nextSpec.exercise_id, signal);
      if (signal?.aborted) return;
      try {
        const nextCapabilities = await api<Capabilities>(
          "/learning/execution-capabilities",
          { signal },
        );
        if (!signal?.aborted) setCapabilities(nextCapabilities);
      } catch {
        if (!signal?.aborted) setCapabilities(null);
      }
    } catch (reason) {
      if (signal?.aborted) return;
      setError(
        reason instanceof ApiError && reason.status === 404
          ? "Для этого урока отдельное задание с кодом пока не опубликовано. Можно выполнить практику из материала и объяснить решение своими словами."
          : errorMessage(reason),
      );
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [history, lessonId, userId]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => {
      controller.abort();
      ++historyRequest.current;
    };
  }, [load]);

  useEffect(() => {
    if (!focusRequest) return;
    const frame = window.requestAnimationFrame(() => {
      practiceRef.current
        ?.querySelector<HTMLElement>("#source-code .cm-content")
        ?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [focusRequest]);

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

  function changeSource(value: string, backupSource = draftBackup?.key === draftKey ? draftBackup.source : null) {
    if (sync.isAccountInvalid() || value.length > SOURCE_LIMIT) return;
    setSource(value);
    setHasLocalDraft(true);
    sync.changed({ source_code: value, backup_source: backupSource });
    if (draftKey)
      try {
        window.localStorage.setItem(draftKey, value);
      } catch {
        /* Storage is optional. */
      }
  }

  function preserveDraftBeforeReplacement(): boolean {
    if (!draftKey || source.length > SOURCE_LIMIT) return false;
    try {
      window.localStorage.setItem(`${draftKey}.backup`, source);
    } catch {
      setRestoreError(
        "Не удалось сохранить предыдущий черновик в браузере. Замена отменена, текущий код остался в редакторе. Проверьте доступ к локальному хранилищу и повторите действие.",
      );
      setRestoreMessage("");
      return false;
    }
    setDraftBackup({ key: draftKey, source });
    setRestoreError("");
    return true;
  }

  function restoreAttempt(attempt: AttemptSource): boolean {
    if (
      !spec || !draftKey || busy || sync.isAccountInvalid() || pending || (job && ACTIVE.has(job.status)) ||
      !attempt.version_verified || attempt.exercise_id !== spec.exercise_id ||
      attempt.exercise_version !== spec.version || attempt.language !== CODE_LANGUAGE ||
      attempt.mode !== CODE_MODE || attempt.source_code.length > SOURCE_LIMIT
    ) return false;
    if (source !== attempt.source_code && !preserveDraftBeforeReplacement())
      return false;
    changeSource(attempt.source_code, source !== attempt.source_code ? source : draftBackup?.source ?? null);
    setRestoreError("");
    setRestoreMessage("Код восстановлен в редакторе. Сохраните новую попытку, когда будете готовы.");
    setFocusRequest((value) => value + 1);
    return true;
  }

  function restorePreviousDraft() {
    if (
      !draftBackup || draftBackup.key !== draftKey || busy || sync.isAccountInvalid() || pending ||
      (job && ACTIVE.has(job.status))
    ) return;
    // Swap the two drafts so restoring the backup also preserves later edits.
    const previous = draftBackup.source;
    if (!preserveDraftBeforeReplacement()) return;
    changeSource(previous, source);
    setRestoreMessage("Предыдущий черновик возвращён в редактор. Заменённый текст доступен ниже.");
    setFocusRequest((value) => value + 1);
  }

  async function send(submission: Submission) {
    if (!spec || busy || sync.isAccountInvalid() || !sync.guardHeaders) return;
    sync.changed({ source_code: source, backup_source: draftBackup?.key === draftKey ? draftBackup.source : null });
    setBusy(true);
    setError("");
    setPending(submission);
    try {
      const next = await api<Job>(
        `/learning/exercises/${encodeURIComponent(spec.exercise_id)}/jobs`,
        {
          method: "POST",
          headers: { ...sync.guardHeaders, "Idempotency-Key": submission.key },
          body: JSON.stringify({
            language: CODE_LANGUAGE,
            mode: CODE_MODE,
            source_code: submission.source,
          }),
        },
      );
      setPending(null);
      setJob(next);
      setPollStopped(false);
      await history(spec.exercise_id);
    } catch (reason) {
      if (sync.handleAccountError(reason)) return;
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (sync.isAccountInvalid()) return;
    if (source.trim()) void send(pending ?? { key: newRequestId(), source });
  }

  async function cancel() {
    if (!job || busy || sync.isAccountInvalid() || !sync.guardHeaders) return;
    setBusy(true);
    try {
      const next = await api<Job>(
        `/learning/jobs/${encodeURIComponent(job.id)}/cancel`,
        { method: "POST", headers: sync.guardHeaders },
      );
      setJob(next);
      await history(next.exercise_id);
    } catch (reason) {
      if (sync.handleAccountError(reason)) return;
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      ref={practiceRef}
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
            busy={busy || accountChanged}
            disabled={accountChanged || !sync.guardHeaders || !!pending || (!!job && ACTIVE.has(job.status))}
            executionConfigured={capabilities?.configured ?? false}
          />
          <DraftSyncStatus
            sync={sync}
            preview={(value) => `${value.source_code || "Пустой код."}${value.backup_source !== null ? `\n\nПредыдущий черновик кода:\n${value.backup_source}` : ""}`}
            disabled={busy || accountChanged || !!pending || (!!job && ACTIVE.has(job.status))}
          />
          {restoreMessage && <p role="status">{restoreMessage}</p>}
          {restoreError && <p className="form-error" role="alert">{restoreError}</p>}
          {draftBackup && draftBackup.key === draftKey && (
            <details className="lesson-detail">
              <summary>Предыдущий черновик</summary>
              <p className="muted">
                Сохранён до замены кода в этом браузере и доступен при повторном
                открытии урока. При возврате текущий код останется здесь как
                предыдущий черновик. Выход из аккаунта удаляет локальные черновики.
              </p>
              <pre className="attempt-source-preview" tabIndex={0} aria-label="Предыдущий черновик кода">
                <code>{draftBackup.source}</code>
              </pre>
              <button
                className="text-button"
                type="button"
                disabled={busy || accountChanged || !!pending || (!!job && ACTIVE.has(job.status))}
                onClick={restorePreviousDraft}
              >
                Вернуть предыдущий черновик
              </button>
            </details>
          )}
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
              disabled={busy || accountChanged || !sync.guardHeaders}
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
                disabled={accountChanged}
                onClick={() => setPollStopped(false)}
              >
                Продолжить проверку статуса
              </button>
            </p>
          )}
          <details className="lesson-detail">
            <summary>История попыток ({attempts.length})</summary>
            {historyLoading && <p role="status">Обновляем историю попыток…</p>}
            {historyError && (
              <div role="alert">
                <p className="form-error">{historyError}</p>
                <button
                  className="text-button"
                  type="button"
                  disabled={historyLoading || accountChanged}
                  onClick={() => void history(spec.exercise_id)}
                >
                  Обновить историю
                </button>
              </div>
            )}
            {(!historyLoading || attempts.length > 0) && (!historyError || attempts.length > 0) && (
              <AttemptHistory
                key={draftKey}
                attempts={attempts}
                currentSource={source}
                restoreTarget={{
                  exercise_id: spec.exercise_id,
                  version: spec.version,
                  language: CODE_LANGUAGE,
                  mode: CODE_MODE,
                  maxSourceLength: SOURCE_LIMIT,
                }}
                restoreDisabled={busy || accountChanged || !!pending || (!!job && ACTIVE.has(job.status))}
                onRestore={restoreAttempt}
              />
            )}
          </details>
        </>
      )}
      {error && (
        <div role="alert">
          <p className="form-error">{error}</p>
          {pending ? (
            <>
              <button
                className="text-button"
                disabled={busy || accountChanged || !sync.guardHeaders}
                onClick={() => void send(pending)}
              >
                Повторить отправку
              </button>
              <button
                className="text-button"
                disabled={busy || accountChanged}
                onClick={() => { if (!sync.isAccountInvalid()) setPending(null); }}
              >
                Изменить решение
              </button>
            </>
          ) : (
            !spec && (
              <button
                className="text-button"
                disabled={loading || accountChanged}
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
