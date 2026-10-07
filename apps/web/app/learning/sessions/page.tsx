"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import AppHeader from "../../components/app-header";
import StudySessionPanel, { SessionFocus, STUDY_SESSION_LABELS } from "../../components/study-session-panel";
import { studyDuration, useStudySession, type StudySession } from "../../components/study-session-provider";
import { api, ApiError, errorMessage, isUnauthorized } from "../../lib/api";

function localTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Дата недоступна"
    : date.toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" });
}

export default function StudySessionsPage() {
  const router = useRouter();
  const { ownerId, accountScope, eligible, loading: accountLoading, historyRevision, refresh: refreshSession, clear } = useStudySession();
  const [sessions, setSessions] = useState<StudySession[]>([]);
  const [loadedScope, setLoadedScope] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [limit, setLimit] = useState<20 | 50>(20);
  const [requestNumber, setRequestNumber] = useState(0);
  const requestGeneration = useRef(0);
  const visibleSessions = loadedScope === accountScope && !accountLoading ? sessions : [];

  useEffect(() => {
    const generation = ++requestGeneration.current;
    const controller = new AbortController();
    setSessions([]);
    setLoadedScope(null);
    setError("");
    if (accountLoading || !ownerId || !accountScope || !eligible) {
      setLoading(accountLoading);
      return () => controller.abort();
    }
    setLoading(true);
    void api<StudySession[]>(`/learning/study-sessions?limit=${limit}`, {
      signal: controller.signal,
      cache: "no-store",
      headers: { "X-Account-Scope": accountScope },
    }).then((result) => {
      if (!controller.signal.aborted && requestGeneration.current === generation) {
        setLoadedScope(accountScope);
        setSessions(result);
      }
    }).catch((reason) => {
      if (controller.signal.aborted || requestGeneration.current !== generation) return;
      if (isUnauthorized(reason)) {
        clear();
        router.replace("/auth");
      } else if (reason instanceof ApiError && reason.code === "account_changed") {
        clear();
        window.dispatchEvent(new CustomEvent("mentor:auth-changed"));
      } else setError(errorMessage(reason));
    }).finally(() => {
      if (!controller.signal.aborted && requestGeneration.current === generation) setLoading(false);
    });
    return () => controller.abort();
  }, [ownerId, accountScope, eligible, accountLoading, limit, historyRevision, requestNumber, router, clear]);

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="page-content">
        <header className="page-heading">
          <div>
            <span className="page-kicker">Ваш учебный ритм</span>
            <h1>История занятий</h1>
            <p className="page-subtitle">Сохранённые планы, паузы и время по таймеру на всех ваших устройствах.</p>
          </div>
          <button className="button-secondary" type="button" disabled={accountLoading || loading} onClick={() => {
            setRequestNumber((value) => value + 1);
            void refreshSession();
          }}>Обновить историю</button>
        </header>
        <StudySessionPanel />
        <section className="panel study-session-history" aria-labelledby="study-history-title" aria-busy={accountLoading || loading}>
          <div className="panel-heading">
            <div>
              <p className="page-kicker">Сохранено на сервере</p>
              <h2 id="study-history-title">Последние занятия</h2>
            </div>
            <div className="study-history-limit">
              <label htmlFor="study-history-limit">Показать</label>
              <select id="study-history-limit" value={limit} onChange={(event) => setLimit(Number(event.target.value) as 20 | 50)}>
                <option value={20}>20 последних занятий</option>
                <option value={50}>50 последних занятий</option>
              </select>
            </div>
          </div>
          <p className="product-section-intro">
            Время показано в часовом поясе устройства. Занятие не заменяет проверку урока: завершение таймера не добавляет оценки или учебного результата.
          </p>
          {accountLoading || loading ? (
            <p className="status-message" role="status">Загружаем историю занятий…</p>
          ) : error ? (
            <div className="study-session-error" role="alert">
              <p>{error}</p>
              <button className="button-secondary" type="button" onClick={() => setRequestNumber((value) => value + 1)}>Повторить загрузку истории</button>
            </div>
          ) : !ownerId ? (
            <p className="muted">История станет доступна после загрузки аккаунта.</p>
          ) : !eligible ? (
            <p className="muted">История появится после настройки обучения и первого занятия.</p>
          ) : visibleSessions.length === 0 ? (
            <div className="empty-state">
              <h3>Пока нет сохранённых занятий</h3>
              <p>Начните занятие кнопкой выше, когда будете готовы учиться. Уроки доступны и без таймера.</p>
            </div>
          ) : (
            <ol className="study-session-history-list">
              {visibleSessions.map((item) => (
                <li key={item.id}>
                  <article>
                    <div className="study-history-heading">
                      <div>
                        <span className={`badge study-session-state-badge is-${item.status}`}>{STUDY_SESSION_LABELS[item.status]}</span>
                        <h3><time dateTime={item.started_at}>{localTime(item.started_at)}</time></h3>
                        {item.ended_at && <p className="muted">Окончание: <time dateTime={item.ended_at}>{localTime(item.ended_at)}</time></p>}
                      </div>
                      <dl className="study-history-duration">
                        <dt>Время по таймеру</dt>
                        <dd>{studyDuration(item.active_seconds)}</dd>
                      </dl>
                    </div>
                    <details className="product-disclosure study-session-plan">
                      <summary>План на момент начала занятия</summary>
                      <p className="muted">Примерная длительность плана: {item.estimated_minutes} минут. Пункты плана не являются отметками о выполнении.</p>
                      <SessionFocus session={item} />
                    </details>
                  </article>
                </li>
              ))}
            </ol>
          )}
          {!loading && !error && visibleSessions.length === limit && (
            <p className="muted">Показаны {limit} последних занятий.{limit === 20 ? " Можно увеличить список до 50 записей." : " Старые записи остаются сохранёнными на сервере."}</p>
          )}
        </section>
      </div>
    </main>
  );
}
