"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import AppHeader from "../components/app-header";
import { api, errorMessage, newRequestId } from "../lib/api";
import { useUser } from "../lib/use-user";

type MilestoneTemplate = { id: string; title: string; required_sections: string[]; instructions: string };
type Template = { id: string; version: string | number; title: string; skill_ids: string[]; requirements: string[]; milestones: MilestoneTemplate[] };
type Submission = { id: string; milestone_id: string; validation: { status: "needs_revision" | "artifact_received"; missing_sections: string[]; execution_status: "not_executed"; mastery_credit: false; message: string }; repository_url: string | null; created_at: string };
type Portfolio = { published: boolean; title: string; summary: string; repository_url: string | null; public_path?: string | null };
type Project = { id: string; template: Template; milestones: (MilestoneTemplate & { latest_submission?: Submission | null })[]; created_at: string; portfolio?: Portfolio | null; notice: string };

export default function ProjectsPage() {
  const { user, loading, error: userError, reload } = useUser(true);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [current, setCurrent] = useState<Project | null>(null);
  const [loadBusy, setLoadBusy] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const pending = useRef<Record<string, { fingerprint: string; key: string }>>({});
  const load = useCallback(async () => {
    setLoadBusy(true); setError("");
    try { const [catalog, saved] = await Promise.all([api<Template[]>("/projects/templates"), api<Project[]>("/projects")]); setTemplates(catalog); setProjects(saved); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setLoadBusy(false); }
  }, []);
  useEffect(() => { if (user) void load(); }, [user, load]);

  async function action(operation: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(""); setStatus("");
    try { await operation(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  async function refreshCurrent(id: string) { setCurrent(await api<Project>(`/projects/${encodeURIComponent(id)}`)); }
  function submitMilestone(event: FormEvent<HTMLFormElement>, milestoneId: string) {
    event.preventDefault();
    if (!current) return;
    const data = new FormData(event.currentTarget);
    const payload = { artifact_text: String(data.get("artifact_text")), repository_url: data.get("repository_url") || null };
    const scope = `${current.id}.${milestoneId}`;
    const fingerprint = JSON.stringify(payload);
    if (pending.current[scope]?.fingerprint !== fingerprint) pending.current[scope] = { fingerprint, key: newRequestId() };
    void action(async () => {
      const result = await api<Submission>(`/projects/${encodeURIComponent(current.id)}/milestones/${encodeURIComponent(milestoneId)}/submissions`, { method: "POST", body: JSON.stringify({ ...payload, idempotency_key: pending.current[scope].key }) });
      delete pending.current[scope];
      await refreshCurrent(current.id);
      setStatus(result.validation.message);
    });
  }
  function savePortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!current) return;
    const data = new FormData(event.currentTarget);
    void action(async () => {
      const result = await api<Portfolio>(`/projects/${encodeURIComponent(current.id)}/portfolio`, { method: "PATCH", body: JSON.stringify({ published: data.has("published"), title: data.get("title"), summary: data.get("summary"), repository_url: data.get("repository_url") || null }) });
      setCurrent({ ...current, portfolio: result });
      setStatus(result.published ? "Портфолио опубликовано. Проверьте данные по публичной ссылке." : "Портфолио сохранено без публичного доступа.");
    });
  }
  return <main className="dashboard-shell"><AppHeader /><section className="dashboard-card"><h1>Backend-проекты</h1><p className="auth-lead">Соберите проект по этапам и сохраните материалы. Сейчас проверяется комплектность разделов; код и репозиторий не выполняются, а самостоятельное освоение не оценивается по тексту.</p>
    {loading && <p role="status">Проверяем аккаунт…</p>}{userError && <div role="alert"><p>{userError}</p><button className="text-button" onClick={() => void reload()}>Повторить</button></div>}
    {error && <div role="alert"><p className="form-error">{error}</p><button className="text-button" disabled={busy || loadBusy} onClick={() => void load()}>Обновить список</button></div>}{status && <p role="status">{status}</p>}
    {user && <>{loadBusy && <p role="status">Загружаем проекты…</p>}<section className="lesson-subsection"><h2>Начать проект</h2>{!loadBusy && templates.length === 0 && !error && <p>Шаблоны пока не опубликованы.</p>}<div className="product-list">{templates.map((template) => <article className="saved-item" key={template.id}><h3>{template.title}</h3><ul>{template.requirements.map((requirement) => <li key={requirement}>{requirement}</li>)}</ul><p>{template.milestones.length} этапов</p><button className="text-button" disabled={busy} onClick={() => void action(async () => { const project = await api<Project>("/projects", { method: "POST", body: JSON.stringify({ template_id: template.id }) }); setCurrent(project); await load(); setStatus("Проект создан."); })}>Создать проект</button></article>)}</div></section>
      <section className="lesson-subsection"><h2>Ваши проекты</h2>{!loadBusy && projects.length === 0 && !error && <p>Создайте первый проект по шаблону выше.</p>}<ul>{projects.map((project) => <li key={project.id}><button className="text-button" disabled={busy} onClick={() => void action(() => refreshCurrent(project.id))}>{project.template.title} · {new Date(project.created_at).toLocaleDateString("ru-RU")}</button></li>)}</ul></section>
      {current && <section className="lesson-subsection"><h2>{current.template.title}</h2><p className="muted">{current.notice}</p>{current.milestones.map((milestone) => <article className="saved-item" key={`${current.id}.${milestone.id}`}><h3>{milestone.title}</h3><p className="preserve-lines">{milestone.instructions}</p><p>Обязательные разделы: {milestone.required_sections.join(", ")}.</p><form className="settings-form" onSubmit={(event) => submitMilestone(event, milestone.id)}><label>Материал этапа<textarea name="artifact_text" required minLength={30} maxLength={25000} rows={7} disabled={busy} placeholder="Описание, выдержки кода, проверки и результаты…" /></label><label>Ссылка на репозиторий, необязательно<input name="repository_url" type="url" pattern="https://.*" maxLength={2000} disabled={busy} /></label><button className="form-button" disabled={busy}>{busy ? "Сохраняем…" : "Отправить материал этапа"}</button></form>{milestone.latest_submission && <div className="review-result"><p>{milestone.latest_submission.validation.message}</p>{milestone.latest_submission.validation.missing_sections.length > 0 && <p>Добавьте разделы: {milestone.latest_submission.validation.missing_sections.join(", ")}.</p>}<p className="muted">Код не выполнялся. Этот разбор не начисляет credit за освоение.</p></div>}</article>)}
        <h3>Портфолио</h3><p className="muted">Публичная страница содержит только указанные ниже название, описание и ссылку. Проверьте, что они не содержат секретов и личных данных.</p><form className="settings-form" key={`portfolio.${current.id}`} onSubmit={savePortfolio}><label>Название<input name="title" defaultValue={current.portfolio?.title ?? current.template.title} required minLength={2} maxLength={160} disabled={busy} /></label><label>Описание<textarea name="summary" defaultValue={current.portfolio?.summary ?? ""} required minLength={10} maxLength={2000} rows={4} disabled={busy} /></label><label>Ссылка на репозиторий<input name="repository_url" defaultValue={current.portfolio?.repository_url ?? ""} type="url" pattern="https://.*" maxLength={2000} disabled={busy} /></label><label className="check-label"><input name="published" type="checkbox" defaultChecked={current.portfolio?.published ?? false} disabled={busy} />Опубликовать описание для всех, у кого есть ссылка</label><button className="form-button" disabled={busy}>Сохранить портфолио</button></form>{current.portfolio?.published && current.portfolio.public_path?.startsWith("/portfolio/") && <p><a href={current.portfolio.public_path} target="_blank" rel="noopener noreferrer">Открыть публичное портфолио</a></p>}
        <details><summary>Удалить проект</summary><p>Проект и сохранённые материалы будут удалены. Публичная страница станет недоступна.</p><button className="text-button" disabled={busy} onClick={() => void action(async () => { await api<void>(`/projects/${encodeURIComponent(current.id)}`, { method: "DELETE" }); setCurrent(null); await load(); setStatus("Проект удалён."); })}>Удалить этот проект</button></details>
      </section>}
    </>}
  </section></main>;
}
