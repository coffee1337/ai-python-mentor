"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import AppHeader from "../components/app-header";
import { api, errorMessage, newRequestId } from "../lib/api";
import { useUser } from "../lib/use-user";

type MilestoneTemplate = {
  id: string;
  title: string;
  required_sections: string[];
  instructions: string;
};
type Template = {
  id: string;
  version: string | number;
  title: string;
  skill_ids: string[];
  requirements: string[];
  milestones: MilestoneTemplate[];
};
type Submission = {
  id: string;
  milestone_id: string;
  validation: {
    status: "needs_revision" | "artifact_received";
    missing_sections: string[];
    execution_status: "not_executed";
    mastery_credit: false;
    message: string;
  };
  repository_url: string | null;
  created_at: string;
};
type Portfolio = {
  published: boolean;
  title: string;
  summary: string;
  repository_url: string | null;
  public_path?: string | null;
};
type Project = {
  id: string;
  template: Template;
  milestones: (MilestoneTemplate & { latest_submission?: Submission | null })[];
  created_at: string;
  portfolio?: Portfolio | null;
  notice: string;
};

function submissionStatus(submission?: Submission | null) {
  if (!submission) return "Ожидает материал";
  return submission.validation.status === "artifact_received"
    ? "Материал принят"
    : "Нужно дополнить";
}

export default function ProjectsPage() {
  const { user, loading, error: userError, reload } = useUser(true);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [current, setCurrent] = useState<Project | null>(null);
  const [loadBusy, setLoadBusy] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const pending = useRef<Record<string, { fingerprint: string; key: string }>>(
    {},
  );

  const load = useCallback(async () => {
    setLoadBusy(true);
    setError("");
    try {
      const [catalog, saved] = await Promise.all([
        api<Template[]>("/projects/templates"),
        api<Project[]>("/projects"),
      ]);
      setTemplates(catalog);
      setProjects(saved);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoadBusy(false);
    }
  }, []);

  useEffect(() => {
    if (user) void load();
  }, [user, load]);

  async function action(operation: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await operation();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function refreshCurrent(id: string) {
    setCurrent(await api<Project>(`/projects/${encodeURIComponent(id)}`));
  }

  function createProject(template: Template) {
    void action(async () => {
      const project = await api<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ template_id: template.id }),
      });
      setCurrent(project);
      await load();
      setStatus(
        "Проект создан. Откройте первый этап и начните с описания задачи.",
      );
    });
  }

  function submitMilestone(
    event: FormEvent<HTMLFormElement>,
    milestoneId: string,
  ) {
    event.preventDefault();
    if (!current) return;
    const data = new FormData(event.currentTarget);
    const payload = {
      artifact_text: String(data.get("artifact_text")),
      repository_url: data.get("repository_url") || null,
    };
    const scope = `${current.id}.${milestoneId}`;
    const fingerprint = JSON.stringify(payload);
    if (pending.current[scope]?.fingerprint !== fingerprint) {
      pending.current[scope] = { fingerprint, key: newRequestId() };
    }
    void action(async () => {
      const result = await api<Submission>(
        `/projects/${encodeURIComponent(current.id)}/milestones/${encodeURIComponent(milestoneId)}/submissions`,
        {
          method: "POST",
          body: JSON.stringify({
            ...payload,
            idempotency_key: pending.current[scope].key,
          }),
        },
      );
      delete pending.current[scope];
      await refreshCurrent(current.id);
      await load();
      setStatus(result.validation.message);
    });
  }

  function savePortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!current) return;
    const data = new FormData(event.currentTarget);
    void action(async () => {
      const result = await api<Portfolio>(
        `/projects/${encodeURIComponent(current.id)}/portfolio`,
        {
          method: "PATCH",
          body: JSON.stringify({
            published: data.has("published"),
            title: data.get("title"),
            summary: data.get("summary"),
            repository_url: data.get("repository_url") || null,
          }),
        },
      );
      setCurrent({ ...current, portfolio: result });
      setStatus(
        result.published
          ? "Портфолио опубликовано. Проверьте описание по публичной ссылке."
          : "Портфолио сохранено без публичного доступа.",
      );
    });
  }

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="product-page">
        <header className="page-heading">
          <div>
            <p className="page-kicker">От знаний к практике</p>
            <h1>Ваши Backend-проекты</h1>
            <p className="page-subtitle">
              Пройдите от идеи до описания готовой работы: по небольшим этапам,
              с понятными требованиями к каждому.
            </p>
          </div>
          <a className="button button-secondary" href="/learning/path">
            Учебный путь
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
              Обновить проекты
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
            <section className="panel projects-intro-panel">
              <div>
                <p className="page-kicker">Как это работает</p>
                <h2>Проект — следующий шаг после основ</h2>
                <p>
                  Если вы пока не пишете код, начните с уроков Python.
                  Возвращайтесь к проекту, когда захотите соединить знакомые
                  темы в одну работу.
                </p>
              </div>
              <ol className="projects-process">
                <li>
                  <span className="product-step-number">1</span>
                  <span>Выберите шаблон</span>
                </li>
                <li>
                  <span className="product-step-number">2</span>
                  <span>Соберите материалы этапов</span>
                </li>
                <li>
                  <span className="product-step-number">3</span>
                  <span>Оформите портфолио</span>
                </li>
              </ol>
            </section>

            <section aria-labelledby="saved-projects-title">
              <div className="product-section-heading">
                <div>
                  <h2 id="saved-projects-title">Мои проекты</h2>
                  <p className="product-section-intro">
                    Продолжите работу с того этапа, на котором остановились.
                  </p>
                </div>
                <span className="badge">{projects.length}</span>
              </div>
              {loadBusy && <p role="status">Загружаем проекты…</p>}
              {!loadBusy && projects.length === 0 && !error && (
                <div className="panel empty-state projects-empty">
                  <span className="product-empty-icon" aria-hidden="true">
                    ⌘
                  </span>
                  <div>
                    <h3>Первый проект ещё впереди</h3>
                    <p>
                      Выберите подходящий шаблон ниже. Требования помогут
                      понять, что вы будете делать.
                    </p>
                  </div>
                  <a
                    className="button button-secondary"
                    href="#project-templates"
                  >
                    Посмотреть шаблоны
                  </a>
                </div>
              )}
              <div className="projects-saved-grid">
                {projects.map((project) => (
                  <button
                    className={`panel project-saved-card ${current?.id === project.id ? "is-selected" : ""}`}
                    key={project.id}
                    disabled={busy}
                    aria-pressed={current?.id === project.id}
                    onClick={() =>
                      void action(() => refreshCurrent(project.id))
                    }
                  >
                    <span className="product-inline-heading">
                      <strong>{project.template.title}</strong>
                      <span aria-hidden="true">→</span>
                    </span>
                    <span className="product-field-hint">
                      Создан{" "}
                      {new Date(project.created_at).toLocaleDateString("ru-RU")}
                    </span>
                    <span>
                      {
                        project.milestones.filter(
                          (milestone) =>
                            milestone.latest_submission?.validation.status ===
                            "artifact_received",
                        ).length
                      }{" "}
                      из {project.milestones.length} этапов с принятым
                      материалом
                    </span>
                  </button>
                ))}
              </div>
            </section>

            {current && (
              <section
                className="panel project-workspace"
                aria-labelledby="current-project-title"
              >
                <div className="panel-heading">
                  <div>
                    <p className="page-kicker">Рабочее пространство</p>
                    <h2 id="current-project-title">{current.template.title}</h2>
                  </div>
                  <span className="badge">
                    {current.milestones.length} этапов
                  </span>
                </div>
                <p className="product-section-intro">{current.notice}</p>
                <div className="project-check-notice">
                  <strong>Что проверяется при отправке</strong>
                  <p>
                    Проверяется наличие нужных разделов в вашем материале. Код и
                    репозиторий не запускаются; принятие материала не
                    подтверждает правильность решения или самостоятельное
                    освоение навыка.
                  </p>
                </div>

                <div className="project-milestones">
                  {current.milestones.map((milestone, index) => (
                    <details
                      className="project-milestone"
                      key={`${current.id}.${milestone.id}`}
                      open={index === 0 ? true : undefined}
                    >
                      <summary>
                        <span
                          className="product-step-number"
                          aria-hidden="true"
                        >
                          {index + 1}
                        </span>
                        <span className="project-milestone-title">
                          <strong>{milestone.title}</strong>
                          <small>
                            Этап {index + 1} из {current.milestones.length}
                          </small>
                        </span>
                        <span
                          className={`badge ${milestone.latest_submission?.validation.status === "artifact_received" ? "product-badge-positive" : "product-badge-neutral"}`}
                        >
                          {submissionStatus(milestone.latest_submission)}
                        </span>
                      </summary>
                      <div className="project-milestone-content">
                        <h3>Что нужно сделать</h3>
                        <p className="product-preserve-lines">
                          {milestone.instructions}
                        </p>
                        <h3>Как оформить результат</h3>
                        <p className="product-section-intro">
                          Напишите каждый раздел отдельным заголовком и добавьте
                          под ним своё описание, код или результаты проверки.
                        </p>
                        <ul className="project-section-chips">
                          {milestone.required_sections.map((section) => (
                            <li key={section}>{section}</li>
                          ))}
                        </ul>
                        <form
                          className="settings-form"
                          onSubmit={(event) =>
                            submitMilestone(event, milestone.id)
                          }
                        >
                          <fieldset disabled={busy}>
                            <label>
                              Материал этапа
                              <textarea
                                name="artifact_text"
                                required
                                minLength={30}
                                maxLength={25000}
                                rows={8}
                                placeholder={milestone.required_sections
                                  .map(
                                    (section) =>
                                      `## ${section}\nВаше описание и результаты…`,
                                  )
                                  .join("\n\n")}
                              />
                              <span className="product-field-hint">
                                Разделы должны называться точно как в списке
                                выше. Не добавляйте пароли и ключи.
                              </span>
                            </label>
                            <label>
                              Ссылка на репозиторий{" "}
                              <span className="optional">необязательно</span>
                              <input
                                name="repository_url"
                                type="url"
                                pattern="https://.*"
                                maxLength={2000}
                                placeholder="https://github.com/…"
                              />
                            </label>
                          </fieldset>
                          <button className="button" disabled={busy}>
                            {busy
                              ? "Обрабатываем запрос…"
                              : milestone.latest_submission
                                ? "Отправить обновлённый материал"
                                : "Отправить материал этапа"}
                          </button>
                        </form>
                        {milestone.latest_submission && (
                          <div
                            className={`project-submission-result ${milestone.latest_submission.validation.status === "artifact_received" ? "product-success" : "product-revision"}`}
                          >
                            <div className="product-inline-heading">
                              <strong>
                                {submissionStatus(milestone.latest_submission)}
                              </strong>
                              <span className="product-field-hint">
                                {new Date(
                                  milestone.latest_submission.created_at,
                                ).toLocaleDateString("ru-RU")}
                              </span>
                            </div>
                            <p>
                              {milestone.latest_submission.validation.message}
                            </p>
                            {milestone.latest_submission.validation
                              .missing_sections.length > 0 && (
                              <p>
                                Добавьте заголовки и содержание разделов:{" "}
                                <strong>
                                  {milestone.latest_submission.validation.missing_sections.join(
                                    ", ",
                                  )}
                                </strong>
                                .
                              </p>
                            )}
                            <p className="product-field-hint">
                              Код не выполнялся. Проверка не меняет оценку
                              освоения навыков.
                            </p>
                          </div>
                        )}
                      </div>
                    </details>
                  ))}
                </div>

                <section
                  className="project-portfolio-section"
                  aria-labelledby="project-portfolio-title"
                >
                  <div className="panel-heading">
                    <div>
                      <p className="page-kicker">Покажите свою работу</p>
                      <h3 id="project-portfolio-title">Портфолио проекта</h3>
                    </div>
                    <span className="badge">
                      {current.portfolio?.published ? "Публичное" : "Приватное"}
                    </span>
                  </div>
                  <p className="product-section-intro">
                    На публичной странице будут только название, описание и
                    ссылка ниже. Материалы этапов и данные аккаунта туда не
                    попадут. Проверьте текст на секреты и личные данные перед
                    публикацией.
                  </p>
                  <form
                    className="settings-form"
                    key={`portfolio.${current.id}`}
                    onSubmit={savePortfolio}
                  >
                    <fieldset disabled={busy}>
                      <div className="product-form-columns">
                        <label>
                          Название проекта
                          <input
                            name="title"
                            defaultValue={
                              current.portfolio?.title ?? current.template.title
                            }
                            required
                            minLength={2}
                            maxLength={160}
                          />
                        </label>
                        <label>
                          Ссылка на репозиторий{" "}
                          <span className="optional">необязательно</span>
                          <input
                            name="repository_url"
                            defaultValue={
                              current.portfolio?.repository_url ?? ""
                            }
                            type="url"
                            pattern="https://.*"
                            maxLength={2000}
                            placeholder="https://github.com/…"
                          />
                        </label>
                      </div>
                      <label>
                        Описание работы
                        <textarea
                          name="summary"
                          defaultValue={current.portfolio?.summary ?? ""}
                          required
                          minLength={10}
                          maxLength={2000}
                          rows={4}
                          placeholder="Какую задачу решает проект, что вы сделали и чему научились?"
                        />
                      </label>
                      <label className="check-label">
                        <input
                          name="published"
                          type="checkbox"
                          defaultChecked={current.portfolio?.published ?? false}
                        />
                        Открыть описание всем, у кого есть публичная ссылка
                      </label>
                    </fieldset>
                    <div className="product-action-row">
                      <button className="button" disabled={busy}>
                        {busy ? "Сохраняем…" : "Сохранить портфолио"}
                      </button>
                      {current.portfolio?.published &&
                        current.portfolio.public_path?.startsWith(
                          "/portfolio/",
                        ) && (
                          <a
                            className="button button-secondary"
                            href={current.portfolio.public_path}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            Посмотреть публичную страницу ↗
                          </a>
                        )}
                    </div>
                  </form>
                </section>

                <details className="product-disclosure product-delete-disclosure">
                  <summary>Удалить проект и материалы</summary>
                  <p>
                    Все материалы проекта будут удалены. Публичная страница
                    перестанет открываться. Учебная история сохранится.
                  </p>
                  <button
                    className="button product-danger-button"
                    disabled={busy}
                    onClick={() =>
                      void action(async () => {
                        await api<void>(
                          `/projects/${encodeURIComponent(current.id)}`,
                          { method: "DELETE" },
                        );
                        setCurrent(null);
                        await load();
                        setStatus("Проект удалён.");
                      })
                    }
                  >
                    Удалить этот проект
                  </button>
                </details>
              </section>
            )}

            <section id="project-templates" aria-labelledby="templates-title">
              <div className="product-section-heading">
                <div>
                  <h2 id="templates-title">Начать новый проект</h2>
                  <p className="product-section-intro">
                    Посмотрите требования и выберите задачу, для которой уже
                    знакомы основные темы.
                  </p>
                </div>
                <span className="badge">{templates.length} шаблонов</span>
              </div>
              {!loadBusy && templates.length === 0 && !error && (
                <div className="panel empty-state">
                  <h3>Шаблоны пока не опубликованы</h3>
                  <p>Продолжайте учебный путь — проекты появятся здесь.</p>
                </div>
              )}
              <div className="project-template-grid">
                {templates.map((template, index) => (
                  <article
                    className="panel project-template-card"
                    key={template.id}
                  >
                    <div className="product-inline-heading">
                      <span
                        className="project-template-icon"
                        aria-hidden="true"
                      >
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <span className="badge">
                        {template.milestones.length} этапов
                      </span>
                    </div>
                    <h3>{template.title}</h3>
                    <ul className="project-template-requirements">
                      {template.requirements.map((requirement) => (
                        <li key={requirement}>{requirement}</li>
                      ))}
                    </ul>
                    <p className="product-field-hint">
                      Тем в учебном графе: {template.skill_ids.length}
                    </p>
                    <button
                      className="button button-secondary"
                      disabled={busy}
                      onClick={() => createProject(template)}
                    >
                      Создать проект <span aria-hidden="true">→</span>
                    </button>
                  </article>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
