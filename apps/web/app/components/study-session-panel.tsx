"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { studyDuration, useStudySession, type StudySession } from "./study-session-provider";

export const STUDY_SESSION_LABELS: Record<StudySession["status"], string> = {
  active: "Идёт занятие",
  paused: "Занятие на паузе",
  completed: "Занятие завершено",
  abandoned: "Занятие отменено",
};

export function SessionFocus({ session }: { session: StudySession }) {
  return (
    <ol className="study-session-focus">
      {session.focus.map((item, index) => (
        <li key={`${item.kind}.${item.lesson_id ?? item.skill_id}.${index}`}>
          <span className="badge">{item.kind === "review" ? "Повторение" : "Урок"}</span>
          <div>
            <strong>{item.title}</strong>
            <span className="muted">Примерно {item.estimated_minutes} минут</span>
          </div>
          {item.kind === "review" ? (
            <Link href="/learning/reviews">Повторить →</Link>
          ) : item.lesson_id ? (
            <Link href={`/learning?lesson=${encodeURIComponent(item.lesson_id)}`}>К уроку →</Link>
          ) : <span className="muted">Материал пока не опубликован</span>}
        </li>
      ))}
    </ol>
  );
}

export default function StudySessionPanel() {
  const { session, elapsedSeconds, ownerId, eligible, loading, busy, error, startBlocked, requiresAction, refresh, action } = useStudySession();
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const titleId = useId();
  const isOpen = session?.status === "active" || session?.status === "paused";

  useEffect(() => {
    setConfirmAbandon(false);
  }, [session?.id, isOpen]);

  return (
    <section className="panel study-session-panel" aria-labelledby={titleId} aria-busy={loading || busy}>
      <div className="panel-heading">
        <div>
          <p className="page-kicker">Ваш темп</p>
          <h2 id={titleId}>Учебное занятие</h2>
        </div>
        <Link className="text-button" href="/learning/sessions">История занятий →</Link>
      </div>
      {loading ? (
        <p className="status-message" role="status">Загружаем сохранённое занятие…</p>
      ) : (
        <>
          {error && (
            <div className="study-session-error" role="alert">
              <p>{error}</p>
              <button className="button-secondary" type="button" disabled={busy} onClick={() => void refresh()}>
                Обновить занятие
              </button>
            </div>
          )}
          {ownerId && !eligible ? (
            <div className="empty-state">
              <h3>Сначала выберите исходный опыт и удобный темп</h3>
              <p>После настройки появится доступный план занятия.</p>
              <Link className="button-secondary" href="/onboarding">Настроить обучение</Link>
            </div>
          ) : session && isOpen ? (
            <>
              <div className="study-session-summary">
                <div className="study-session-clock">
                  <span>Время по таймеру</span>
                  <strong role="timer" aria-label={`Время по таймеру: ${studyDuration(elapsedSeconds)}`}>
                    {studyDuration(elapsedSeconds)}
                  </strong>
                </div>
                <div className="study-session-state">
                  <span className={`badge study-session-state-badge is-${session.status}`} role="status">
                    {STUDY_SESSION_LABELS[session.status]}
                  </span>
                  <p className="muted">
                    {session.status === "active"
                      ? requiresAction
                        ? "После изменения на другом устройстве эта вкладка не продлевает таймер. Нажмите «Пауза», затем продолжите вручную."
                        : "При скрытии вкладки таймер ставится на паузу. Если связь прервётся, сервер остановит отсчёт максимум через минуту."
                      : session.active_seconds >= 8 * 3600
                        ? "Достигнут лимит 8 часов по таймеру. Завершите занятие, затем можно начать новое."
                      : "Отсчёт остановлен. Можно продолжить это занятие или завершить его."}
                  </p>
                </div>
              </div>
              <div className="study-session-actions">
                {session.status === "active" ? (
                  <button className="button-secondary" type="button" disabled={busy} onClick={() => void action("pause")}>
                    Пауза
                  </button>
                ) : (
                  <button className="button" type="button" disabled={busy || session.active_seconds >= 8 * 3600} onClick={() => void action("resume")}>
                    Продолжить занятие
                  </button>
                )}
                <button className="button-secondary" type="button" disabled={busy} onClick={() => void action("finish")}>
                  Завершить занятие
                </button>
                <button className="text-button" type="button" disabled={busy} onClick={() => setConfirmAbandon(true)}>
                  Отменить занятие
                </button>
                {busy && <span className="muted" role="status">Сохраняем состояние…</span>}
              </div>
              {confirmAbandon && (
                <div className="study-session-confirm" role="group" aria-label="Подтверждение отмены занятия">
                  <h3>Отменить это занятие?</h3>
                  <p>Запись останется в истории с пометкой «Отменено». Результаты уроков и сохранённые материалы сохранятся.</p>
                  <div className="study-session-actions">
                    <button className="button-secondary" type="button" disabled={busy} onClick={() => {
                      setConfirmAbandon(false);
                      void action("abandon");
                    }}>Подтвердить отмену</button>
                    <button className="text-button" type="button" disabled={busy} onClick={() => setConfirmAbandon(false)}>Вернуться к занятию</button>
                  </div>
                </div>
              )}
              <details className="product-disclosure study-session-plan">
                <summary>Сохранённый план занятия</summary>
                <p className="muted">
                  План зафиксирован при начале занятия. Примерная длительность: {session.estimated_minutes} минут.
                  {session.target_minutes > 0 ? ` Ориентир вашего темпа: ${session.target_minutes} минут.` : ""}
                  {" "}Таймер не подтверждает выполнение этого плана.
                </p>
                <SessionFocus session={session} />
              </details>
            </>
          ) : eligible && ownerId ? (
            <div className="study-session-start">
              <div>
                {session && <p className="badge" role="status">{STUDY_SESSION_LABELS[session.status]}</p>}
                <h3>{session ? "Можно начать следующее занятие" : "Выделите время для одного учебного шага"}</h3>
                <p className="muted">
                  Начните таймер, когда готовы. Сервер сохранит план и время; пауза позволит продолжить на другом устройстве.
                  {session ? ` В предыдущем занятии по таймеру: ${studyDuration(session.active_seconds)}.` : ""}
                </p>
              </div>
              <button className="button" type="button" disabled={busy || startBlocked} onClick={() => {
                setConfirmAbandon(false);
                void action("start");
              }}>Начать занятие</button>
            </div>
          ) : !error && (
            <p className="muted">Войдите в аккаунт, чтобы сохранить занятие.</p>
          )}
          <p className="study-session-note muted">
            Это время по таймеру, а не измерение внимания или освоения темы. Проверки уроков и прогресс учитываются отдельно.
          </p>
        </>
      )}
    </section>
  );
}
