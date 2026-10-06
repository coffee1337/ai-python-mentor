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
  submissions: Submission[];
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

type Draft = { artifact_text: string; repository_url: string };
type SubmissionSource = Submission & { artifact_text: string };
const DRAFT_PREFIX = "mentor.project.draft.v1.";
const DRAFT_LIMIT = 20;

function readDraft(key: string): Draft {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw && raw.length <= 180000) {
      const value = JSON.parse(raw);
      if (
        value.schema === 1 && typeof value.saved_at === "number" &&
        value.saved_at >= 0 && value.saved_at <= Date.now() &&
        typeof value.artifact_text === "string" && value.artifact_text.length <= 25000 &&
        typeof value.repository_url === "string" && value.repository_url.length <= 2048
      ) {
        return {
          artifact_text: value.artifact_text,
          repository_url: value.repository_url,
        };
      }
    }
    if (raw) window.localStorage.removeItem(key);
  } catch {
    /* Keep the editor usable if browser storage is unavailable. */
  }
  return { artifact_text: "", repository_url: "" };
}

function storeDraft(key: string, draft: Draft): boolean {
  try {
    if (!draft.artifact_text && !draft.repository_url) {
      window.localStorage.removeItem(key);
    } else {
      const existing = window.localStorage.getItem(key) !== null;
      const keys = Object.keys(window.localStorage).filter((item) => item.startsWith(DRAFT_PREFIX));
      // Refuse an additional draft instead of discarding another unsent text.
      if (!existing && keys.length >= DRAFT_LIMIT) return false;
      window.localStorage.setItem(key, JSON.stringify({ schema: 1, saved_at: Date.now(), ...draft }));
    }
    return true;
  } catch {
    return false;
  }
}

function clearProjectDrafts(userId: string, projectId: string) {
  try {
    const prefix = `${DRAFT_PREFIX}${userId}.${projectId}.`;
    for (const key of Object.keys(window.localStorage)) {
      if (key.startsWith(prefix)) window.localStorage.removeItem(key);
    }
  } catch {
    /* Server deletion succeeds even when browser storage is unavailable. */
  }
}

function preferredMilestone(project: Project): string | null {
  const milestone = project.milestones.find((item) => item.latest_submission?.validation.status === "needs_revision") ??
    project.milestones.find((item) => !item.latest_submission) ?? project.milestones[0];
  return milestone?.id ?? null;
}

function rememberProject(projectId: string | null) {
  const url = new URL(window.location.href);
  if (projectId) url.searchParams.set("project", projectId);
  else url.searchParams.delete("project");
  window.history.replaceState(window.history.state, "", url);
}

function MilestoneEditor({
  userId, project, milestone, busy, setBusy, onSubmitted, onNext,
}: {
  userId: string;
  project: Project;
  milestone: Project["milestones"][number];
  busy: boolean;
  setBusy: (value: boolean) => void;
  onSubmitted: (result: Submission) => void;
  onNext: (id: string) => void;
}) {
  const key = `${DRAFT_PREFIX}${userId}.${project.id}.${milestone.id}`;
  const [draft, setDraft] = useState<Draft>({ artifact_text: "", repository_url: "" });
  const [draftLoaded, setDraftLoaded] = useState(false);
  const [draftNote, setDraftNote] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [source, setSource] = useState<SubmissionSource | null>(null);
  const [sourceId, setSourceId] = useState(milestone.latest_submission?.id ?? "");
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState("");
  const [replacePending, setReplacePending] = useState(false);
  const pending = useRef<{ fingerprint: string; key: string } | null>(null);
  const latest = milestone.latest_submission;
  const recent = project.submissions.filter((item) => item.milestone_id === milestone.id);
  const history = latest && !recent.some((item) => item.id === latest.id)
    ? [latest, ...recent]
    : recent;
  const next = project.milestones.find((item) => item.id !== milestone.id && item.latest_submission?.validation.status === "needs_revision") ??
    project.milestones.find((item) => item.id !== milestone.id && !item.latest_submission);

  useEffect(() => {
    const saved = readDraft(key);
    setDraft(saved);
    setDraftLoaded(true);
    if (saved.artifact_text || saved.repository_url) {
      setDraftNote("Восстановлен черновик с этого устройства.");
    }
  }, [key]);

  function edit(value: Draft) {
    setDraft(value);
    setDraftNote(storeDraft(key, value)
      ? "Черновик сохранён на этом устройстве."
      : "Черновик доступен в текущем окне. Отправьте материал или освободите место для черновиков на устройстве.");
    setMessage("");
  }

  async function preview() {
    if (!sourceId || sourceLoading) return;
    setSourceLoading(true);
    setSourceError("");
    setSource(null);
    setReplacePending(false);
    try {
      setSource(await api<SubmissionSource>(
        `/projects/${encodeURIComponent(project.id)}/submissions/${encodeURIComponent(sourceId)}`,
        { cache: "no-store" },
      ));
    } catch (reason) {
      setSourceError(errorMessage(reason));
    } finally {
      setSourceLoading(false);
    }
  }

  function restore() {
    if (!source) return;
    const old = {
      artifact_text: source.artifact_text,
      repository_url: source.repository_url ?? "",
    };
    if (!replacePending && (draft.artifact_text || draft.repository_url) && JSON.stringify(old) !== JSON.stringify(draft)) {
      setReplacePending(true);
      return;
    }
    edit(old);
    setReplacePending(false);
    setMessage("Материал скопирован в черновик. Измените его и отправьте как новую версию.");
    document.getElementById(`artifact-${milestone.id}`)?.focus();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !draftLoaded) return;
    const payload = {
      artifact_text: draft.artifact_text,
      repository_url: draft.repository_url || null,
    };
    const fingerprint = JSON.stringify(payload);
    if (pending.current?.fingerprint !== fingerprint) {
      pending.current = { fingerprint, key: newRequestId() };
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api<Submission>(
        `/projects/${encodeURIComponent(project.id)}/milestones/${encodeURIComponent(milestone.id)}/submissions`,
        {
          method: "POST",
          body: JSON.stringify({ ...payload, idempotency_key: pending.current.key }),
        },
      );
      pending.current = null;
      onSubmitted(result);
      setSourceId(result.id);
      setMessage(result.validation.message);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form className="settings-form" onSubmit={submit}>
        <fieldset disabled={busy || !draftLoaded}>
          <label htmlFor={`artifact-${milestone.id}`}>
            Материал этапа
            <textarea
              id={`artifact-${milestone.id}`}
              name="artifact_text"
              value={draft.artifact_text}
              onChange={(event) => edit({ ...draft, artifact_text: event.target.value })}
              required
              minLength={30}
              maxLength={25000}
              rows={8}
              placeholder={milestone.required_sections
                .map((section) => `## ${section}\nВаше описание и результаты…`)
                .join("\n\n")}
            />
            <span className="product-field-hint">
              Разделы должны называться точно как в списке выше. Не добавляйте пароли и ключи.
            </span>
          </label>
          <label>
            Ссылка на репозиторий <span className="optional">необязательно</span>
            <input
              name="repository_url"
              value={draft.repository_url}
              onChange={(event) => edit({ ...draft, repository_url: event.target.value })}
              type="url"
              pattern="https://.*"
              maxLength={2048}
              placeholder="https://github.com/…"
            />
          </label>
        </fieldset>
        {draftNote && (
          <p className="product-field-hint project-draft-note" role="status">{draftNote}</p>
        )}
        {error && (
          <p className="status-message product-error" role="alert">
            {error} Текст сохранён в форме; повторите отправку.
          </p>
        )}
        <button className="button" disabled={busy || !draftLoaded}>
          {busy ? "Обрабатываем запрос…" : latest
            ? "Отправить обновлённый материал" : "Отправить материал этапа"}
        </button>
      </form>
      {message && <p className="status-message product-success" role="status">{message}</p>}
      {latest && (
        <div className={`project-submission-result ${latest.validation.status === "artifact_received" ? "product-success" : "product-revision"}`}>
          <div className="product-inline-heading">
            <strong>{submissionStatus(latest)}</strong>
            <span className="product-field-hint">
              {new Date(latest.created_at).toLocaleDateString("ru-RU")}
            </span>
          </div>
          <p>{latest.validation.message}</p>
          {latest.validation.missing_sections.length > 0 && (
            <p>
              Добавьте заголовки и содержание разделов: <strong>{latest.validation.missing_sections.join(", ")}</strong>.
            </p>
          )}
          <p className="product-field-hint">
            Код не выполнялся. Проверка не меняет оценку освоения навыков.
          </p>
          {latest.validation.status === "artifact_received" && next && (
            <button className="button button-secondary" disabled={busy} onClick={() => onNext(next.id)}>
              Продолжить: {next.title}
            </button>
          )}
          {latest.validation.status === "artifact_received" && !next && (
            <p>Материалы всех этапов приняты. Можно оформить портфолио ниже.</p>
          )}
        </div>
      )}
      {history.length > 0 && (
        <section className="project-history-panel" aria-labelledby={`history-${milestone.id}`}>
          <h3 id={`history-${milestone.id}`}>Ранее отправленные материалы</h3>
          <p className="product-field-hint">
            Просмотр и копирование не изменяют отправленную версию. Здесь показаны последние материалы проекта.
          </p>
          <label>
            Версия материала
            <select
              value={sourceId}
              disabled={busy || sourceLoading}
              onChange={(event) => {
                setSourceId(event.target.value);
                setSource(null);
                setReplacePending(false);
                setSourceError("");
              }}
            >
              {history.map((item, index) => (
                <option key={item.id} value={item.id}>
                  {new Date(item.created_at).toLocaleString("ru-RU")} · {submissionStatus(item)}{index === 0 ? " · последняя" : ""}
                </option>
              ))}
            </select>
          </label>
          <button
            className="button button-secondary"
            disabled={busy || sourceLoading || !sourceId}
            onClick={() => void preview()}
          >
            {sourceLoading ? "Загружаем материал…" : "Посмотреть материал"}
          </button>
          {sourceError && (
            <div className="status-message product-error" role="alert">
              <p>{sourceError}</p>
              <button className="button button-secondary" onClick={() => void preview()} disabled={sourceLoading}>
                Повторить загрузку материала
              </button>
            </div>
          )}
          {source && (
            <>
              <pre className="project-source-preview">{source.artifact_text}</pre>
              {source.repository_url && (
                <p className="product-preserve-lines">Репозиторий: {source.repository_url}</p>
              )}
              {replacePending ? (
                <div className="project-restore-confirm" role="group" aria-label="Замена текущего черновика">
                  <p>В форме уже есть черновик. Заменить его выбранным материалом и ссылкой?</p>
                  <div className="product-action-row">
                    <button className="button" disabled={busy} onClick={restore}>Заменить черновик</button>
                    <button className="button button-secondary" onClick={() => setReplacePending(false)}>Отмена</button>
                  </div>
                </div>
              ) : (
                <button className="button button-secondary" disabled={busy} onClick={restore}>
                  Скопировать в черновик и редактировать
                </button>
              )}
            </>
          )}
        </section>
      )}
    </>
  );
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
  const [activeMilestone, setActiveMilestone] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadBusy(true);
    setCurrent(null);
    setActiveMilestone(null);
    setError("");
    try {
      const [catalog, saved] = await Promise.all([
        api<Template[]>("/projects/templates"),
        api<Project[]>("/projects"),
      ]);
      setTemplates(catalog);
      setProjects(saved);
      const requested = new URLSearchParams(window.location.search).get("project");
      if (requested) {
        const selected = await api<Project>(`/projects/${encodeURIComponent(requested)}`);
        setCurrent(selected);
        setActiveMilestone(preferredMilestone(selected));
      }
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
    if (busy || loadBusy) return;
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
    const project = await api<Project>(`/projects/${encodeURIComponent(id)}`);
    setCurrent(project);
    setActiveMilestone(preferredMilestone(project));
    rememberProject(project.id);
  }

  function createProject(template: Template) {
    void action(async () => {
      const project = await api<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ template_id: template.id }),
      });
      setCurrent(project);
      setActiveMilestone(preferredMilestone(project));
      rememberProject(project.id);
      await load();
      setStatus(
        "Проект создан. Откройте первый этап и начните с описания задачи.",
      );
    });
  }

  function recordSubmission(result: Submission) {
    if (!current) return;
    const updated = {
      ...current,
      milestones: current.milestones.map((item) => item.id === result.milestone_id ? { ...item, latest_submission: result } : item),
      submissions: [result, ...current.submissions.filter((item) => item.id !== result.id)].slice(0, 100),
    };
    setCurrent(updated);
    setProjects((saved) => saved.map((item) => item.id === updated.id ? updated : item));
  }

  function goToMilestone(id: string) {
    setActiveMilestone(id);
    document.getElementById(`milestone-${id}`)?.focus();
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
                    disabled={busy || loadBusy}
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
                      open={activeMilestone === milestone.id}
                    >
                      <summary
                        id={`milestone-${milestone.id}`}
                        onClick={(event) => {
                          event.preventDefault();
                          if (!busy) setActiveMilestone(activeMilestone === milestone.id ? null : milestone.id);
                        }}
                      >
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
                        <MilestoneEditor
                          key={`${user.id}.${current.id}.${milestone.id}`}
                          userId={user.id}
                          project={current}
                          milestone={milestone}
                          busy={busy || loadBusy}
                          setBusy={setBusy}
                          onSubmitted={recordSubmission}
                          onNext={goToMilestone}
                        />
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
                    <fieldset disabled={busy || loadBusy}>
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
                      <button className="button" disabled={busy || loadBusy}>
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
                    disabled={busy || loadBusy}
                    onClick={() =>
                      void action(async () => {
                        await api<void>(
                          `/projects/${encodeURIComponent(current.id)}`,
                          { method: "DELETE" },
                        );
                        clearProjectDrafts(user.id, current.id);
                        setCurrent(null);
                        rememberProject(null);
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
                      disabled={busy || loadBusy}
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
