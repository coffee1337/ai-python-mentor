"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import AppHeader from "../components/app-header";
import { api, errorMessage } from "../lib/api";
import { useUser } from "../lib/use-user";

type VacancySummary = {
  id: string;
  title: string;
  selected: boolean;
  created_at: string;
};
type Vacancy = VacancySummary & {
  text: string;
  source_url: string | null;
  requirements: {
    skill_id: string;
    level: "required" | "preferred" | "mentioned";
    evidence: string;
  }[];
  roadmap: {
    skill_id: string;
    name: string;
    inferred_prerequisite: boolean;
    observation: "observed" | "not_assessed";
    ready: boolean;
  }[];
  notice: string;
};
const LEVELS = {
  required: "Обязательно",
  preferred: "Желательно",
  mentioned: "Упомянуто",
};

function RoadmapItem({
  step,
  index,
}: {
  step: Vacancy["roadmap"][number];
  index: number;
}) {
  return (
    <li>
      <span className="product-step-number" aria-hidden="true">
        {index + 1}
      </span>
      <div>
        <strong>{step.name}</strong>
        <p>
          {step.inferred_prerequisite
            ? "Основа для следующих тем"
            : "Навык из вакансии"}
        </p>
        <span className="badge">
          {step.ready ? "Можно приступить" : "Сначала изучите основы"}
        </span>
        <small>
          {step.observation === "not_assessed"
            ? "Навык ещё не проверяли в обучении."
            : "Есть учебные наблюдения; это не оценка профессионального уровня."}
        </small>
      </div>
    </li>
  );
}

export default function JobsPage() {
  const { user, loading, error: userError, reload } = useUser(true);
  const [items, setItems] = useState<VacancySummary[]>([]);
  const [current, setCurrent] = useState<Vacancy | null>(null);
  const [loadBusy, setLoadBusy] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const load = useCallback(async () => {
    setLoadBusy(true);
    setError("");
    try {
      setItems(await api<VacancySummary[]>("/vacancies"));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoadBusy(false);
    }
  }, []);

  useEffect(() => {
    if (user) void load();
  }, [user, load]);

  async function open(id: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      setCurrent(await api<Vacancy>(`/vacancies/${encodeURIComponent(id)}`));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const result = await api<Vacancy>("/vacancies", {
        method: "POST",
        body: JSON.stringify({
          title: data.get("title"),
          text: data.get("text"),
          source_url: data.get("source_url") || null,
        }),
      });
      setCurrent(result);
      await load();
      setStatus(
        "Текст проанализирован. Требования и темы для подготовки — ниже.",
      );
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function target() {
    if (!current || busy) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await api(`/vacancies/${encodeURIComponent(current.id)}/target`, {
        method: "POST",
      });
      setCurrent({ ...current, selected: true });
      await load();
      setStatus("Вакансия выбрана как ориентир обучения.");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!current || busy) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await api<void>(`/vacancies/${encodeURIComponent(current.id)}`, {
        method: "DELETE",
      });
      setCurrent(null);
      await load();
      setStatus("Анализ вакансии удалён.");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="product-page">
        <header className="page-heading">
          <div>
            <p className="page-kicker">Карьерный ориентир</p>
            <h1>Чему учиться для вакансии</h1>
            <p className="page-subtitle">
              Разберите требования к работе и свяжите их с темами своего
              учебного маршрута.
            </p>
          </div>
          <a className="button button-secondary" href="/learning/path">
            Мой учебный путь
          </a>
        </header>
        {loading && (
          <div className="panel product-loading" role="status">
            Проверяем аккаунт…
          </div>
        )}
        {userError && (
          <div className="status-message product-error" role="alert">
            <p>{userError}</p>
            <button
              className="button button-secondary"
              onClick={() => void reload()}
            >
              Повторить загрузку
            </button>
          </div>
        )}
        {error && (
          <div className="status-message product-error" role="alert">
            <p>{error}</p>
            <button
              className="button button-secondary"
              disabled={busy || loadBusy}
              onClick={() => void load()}
            >
              Обновить список
            </button>
          </div>
        )}
        {status && (
          <p className="status-message product-success" role="status">
            {status}
          </p>
        )}

        {user && (
          <>
            <div className="jobs-input-grid">
              <section className="panel" aria-labelledby="add-vacancy-title">
                <div className="panel-heading">
                  <div>
                    <p className="page-kicker">Шаг 1</p>
                    <h2 id="add-vacancy-title">Добавьте текст вакансии</h2>
                  </div>
                </div>
                <p className="product-section-intro">
                  Скопируйте обязанности и требования с сайта вакансий.
                  Указывать ссылку необязательно: анализируется вставленный
                  текст.
                </p>
                <form className="settings-form" onSubmit={create}>
                  <fieldset disabled={busy}>
                    <div className="product-form-columns">
                      <label>
                        Название вакансии
                        <input
                          name="title"
                          required
                          minLength={2}
                          maxLength={160}
                          placeholder="Например, Junior Python Backend Developer"
                        />
                      </label>
                      <label>
                        Ссылка на источник{" "}
                        <span className="optional">необязательно</span>
                        <input
                          name="source_url"
                          type="url"
                          maxLength={2000}
                          pattern="https://.*"
                          placeholder="https://…"
                        />
                      </label>
                    </div>
                    <label>
                      Обязанности и требования
                      <textarea
                        name="text"
                        required
                        minLength={20}
                        maxLength={25000}
                        rows={8}
                        placeholder="Вставьте текст вакансии: задачи, необходимые знания и желательные навыки…"
                      />
                      <span className="product-field-hint">
                        Сайт по ссылке автоматически не загружается.
                      </span>
                    </label>
                  </fieldset>
                  <button className="button" disabled={busy}>
                    {busy ? "Обрабатываем запрос…" : "Разобрать требования"}
                  </button>
                </form>
              </section>

              <section
                className="panel jobs-history-panel"
                aria-labelledby="vacancies-history-title"
              >
                <div className="panel-heading">
                  <h2 id="vacancies-history-title">Сохранённые вакансии</h2>
                  <span className="badge">{items.length}</span>
                </div>
                {loadBusy && <p role="status">Загружаем список…</p>}
                {!loadBusy && items.length === 0 && !error && (
                  <div className="empty-state">
                    <span className="product-empty-icon" aria-hidden="true">
                      ↗
                    </span>
                    <h3>Пока нет вакансий</h3>
                    <p>
                      Добавьте первую слева. Разберём знакомые учебному маршруту
                      навыки и покажем темы для подготовки.
                    </p>
                  </div>
                )}
                <ul className="product-selection-list">
                  {items.map((item) => (
                    <li key={item.id}>
                      <button
                        className={`product-selection-button ${current?.id === item.id ? "is-selected" : ""}`}
                        disabled={busy}
                        onClick={() => void open(item.id)}
                        aria-pressed={current?.id === item.id}
                      >
                        <span>
                          <strong>{item.title}</strong>
                          <small>
                            {new Date(item.created_at).toLocaleDateString(
                              "ru-RU",
                            )}
                          </small>
                        </span>
                        {item.selected ? (
                          <span className="badge product-badge-positive">
                            Ориентир
                          </span>
                        ) : (
                          <span aria-hidden="true">→</span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
                <p className="product-field-hint">
                  Анализ не оценивает готовность к трудоустройству. Даже если вы
                  начинаете с нуля, вакансия может быть ориентиром на будущее.
                </p>
              </section>
            </div>

            {current && (
              <section
                className="panel jobs-result-panel"
                aria-labelledby="vacancy-title"
              >
                <div className="panel-heading">
                  <div>
                    <p className="page-kicker">Шаг 2 · Результат анализа</p>
                    <h2 id="vacancy-title">{current.title}</h2>
                  </div>
                  {current.selected && (
                    <span className="badge product-badge-positive">
                      Ваш ориентир
                    </span>
                  )}
                </div>
                <p className="product-section-intro">{current.notice}</p>
                <div className="product-action-row">
                  {!current.selected && (
                    <button
                      className="button"
                      disabled={busy}
                      onClick={() => void target()}
                    >
                      Выбрать ориентиром обучения
                    </button>
                  )}
                  <a className="button button-secondary" href="/learning/path">
                    Открыть учебный путь
                  </a>
                  {current.source_url && (
                    <a
                      className="product-inline-link"
                      href={current.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Источник вакансии ↗
                    </a>
                  )}
                </div>

                <div className="jobs-analysis-grid">
                  <div>
                    <h3>Что требуется в вакансии</h3>
                    <p className="product-field-hint">
                      У каждого совпадения есть фрагмент исходного текста.
                    </p>
                    {current.requirements.length === 0 && (
                      <div className="empty-state">
                        <h3>Совпадений пока нет</h3>
                        <p>
                          В опубликованном учебном графе не найдены навыки из
                          этого текста. Попробуйте добавить более полный список
                          требований.
                        </p>
                      </div>
                    )}
                    <ul className="jobs-requirement-list">
                      {current.requirements.map((item, index) => (
                        <li key={`${item.skill_id}.${index}`}>
                          <div className="product-inline-heading">
                            <strong>
                              {current.roadmap.find(
                                (step) => step.skill_id === item.skill_id,
                              )?.name ?? item.skill_id}
                            </strong>
                            <span className="badge">{LEVELS[item.level]}</span>
                          </div>
                          <blockquote>{item.evidence}</blockquote>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h3>В каком порядке готовиться</h3>
                    <p className="product-field-hint">
                      Сначала основы, затем навыки из вакансии.
                    </p>
                    {current.roadmap.length === 0 && (
                      <p className="product-section-intro">
                        Темы появятся, когда в тексте найдутся знакомые навыки.
                      </p>
                    )}
                    <ol className="jobs-roadmap-list">
                      {current.roadmap.slice(0, 6).map((step, index) => (
                        <RoadmapItem
                          key={step.skill_id}
                          step={step}
                          index={index}
                        />
                      ))}
                    </ol>
                    {current.roadmap.length > 6 && (
                      <details className="product-disclosure jobs-roadmap-disclosure">
                        <summary>
                          Показать остальные темы ({current.roadmap.length - 6})
                        </summary>
                        <ol className="jobs-roadmap-list" start={7}>
                          {current.roadmap.slice(6).map((step, index) => (
                            <RoadmapItem
                              key={step.skill_id}
                              step={step}
                              index={index + 6}
                            />
                          ))}
                        </ol>
                      </details>
                    )}
                  </div>
                </div>

                <details className="product-disclosure">
                  <summary>Посмотреть исходный текст</summary>
                  <p className="product-preserve-lines">{current.text}</p>
                </details>
                <details className="product-disclosure product-delete-disclosure">
                  <summary>Удалить этот анализ</summary>
                  <p>
                    Сохранённый текст и анализ этой вакансии будут удалены.
                    История обучения сохранится.
                  </p>
                  <button
                    className="button product-danger-button"
                    disabled={busy}
                    onClick={() => void remove()}
                  >
                    Удалить анализ вакансии
                  </button>
                </details>
              </section>
            )}
          </>
        )}
      </div>
    </main>
  );
}
