"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import AppHeader from "../components/app-header";
import { api, errorMessage } from "../lib/api";
import { useUser } from "../lib/use-user";

type VacancySummary = { id: string; title: string; selected: boolean; created_at: string };
type Vacancy = VacancySummary & {
  text: string;
  source_url: string | null;
  requirements: { skill_id: string; level: "required" | "preferred" | "mentioned"; evidence: string; start: number; end: number; match_method: string }[];
  roadmap: { skill_id: string; name: string; inferred_prerequisite: boolean; observation: "observed" | "not_assessed"; mastery_signal: number | null; gap: number | null; ready: boolean }[];
  notice: string;
};
const LEVELS = { required: "Требование", preferred: "Желательно", mentioned: "Упомянуто" };
export default function JobsPage() {
  const { user, loading, error: userError, reload } = useUser(true);
  const [items, setItems] = useState<VacancySummary[]>([]);
  const [current, setCurrent] = useState<Vacancy | null>(null);
  const [loadBusy, setLoadBusy] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const load = useCallback(async () => {
    setLoadBusy(true); setError("");
    try { setItems(await api<VacancySummary[]>("/vacancies")); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setLoadBusy(false); }
  }, []);
  useEffect(() => { if (user) void load(); }, [user, load]);
  async function open(id: string) {
    setBusy(true); setError("");
    try { setCurrent(await api<Vacancy>(`/vacancies/${encodeURIComponent(id)}`)); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    setBusy(true); setError(""); setStatus("");
    try { const result = await api<Vacancy>("/vacancies", { method: "POST", body: JSON.stringify({ title: data.get("title"), text: data.get("text"), source_url: data.get("source_url") || null }) }); setCurrent(result); await load(); setStatus("Текст вакансии проанализирован."); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  async function target() {
    if (!current || busy) return;
    setBusy(true); setError("");
    try { await api<unknown>(`/vacancies/${encodeURIComponent(current.id)}/target`, { method: "POST" }); setCurrent({ ...current, selected: true }); await load(); setStatus("Вакансия выбрана как ориентир обучения."); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!current || busy) return;
    setBusy(true); setError("");
    try { await api<void>(`/vacancies/${encodeURIComponent(current.id)}`, { method: "DELETE" }); setCurrent(null); await load(); setStatus("Анализ вакансии удалён."); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <main className="dashboard-shell"><AppHeader /><section className="dashboard-card"><h1>Маршрут под вакансию</h1><p className="auth-lead">Вставьте текст вакансии. Мы сопоставим упомянутые навыки с учебным графом и покажем темы для изучения. Ссылка служит источником; содержимое сайта автоматически не загружается.</p>
    {loading && <p role="status">Проверяем аккаунт…</p>}{userError && <div role="alert"><p>{userError}</p><button className="text-button" onClick={() => void reload()}>Повторить</button></div>}
    {error && <div role="alert"><p className="form-error">{error}</p><button className="text-button" disabled={busy || loadBusy} onClick={() => void load()}>Обновить список</button></div>}{status && <p role="status">{status}</p>}
    {user && <><form className="settings-form" onSubmit={create}><fieldset disabled={busy}><label>Название<input name="title" required minLength={2} maxLength={160} placeholder="Python Backend Developer" /></label><label>Ссылка на источник, необязательно<input name="source_url" type="url" maxLength={2000} pattern="https://.*" placeholder="https://…" /></label><label>Текст вакансии<textarea name="text" required minLength={20} maxLength={25000} rows={9} placeholder="Обязанности, требования и желательные навыки…" /></label></fieldset><button className="form-button" disabled={busy}>{busy ? "Обрабатываем…" : "Проанализировать текст"}</button></form>
      <section className="lesson-subsection"><h2>Сохранённые вакансии</h2>{loadBusy && <p role="status">Загружаем вакансии…</p>}{!loadBusy && items.length === 0 && !error && <p>Пока нет сохранённых вакансий.</p>}<ul>{items.map((item) => <li key={item.id}><button className="text-button" disabled={busy} onClick={() => void open(item.id)}>{item.title}{item.selected ? " · текущий ориентир" : ""}</button></li>)}</ul></section>
      {current && <section className="lesson-subsection" aria-labelledby="vacancy-title"><h2 id="vacancy-title">{current.title}</h2><p className="muted">{current.notice}</p>{current.source_url && <p><a href={current.source_url} target="_blank" rel="noopener noreferrer">Источник вакансии</a></p>}<details><summary>Исходный текст</summary><p className="preserve-lines">{current.text}</p></details><h3>Найденные требования</h3>{current.requirements.length === 0 && <p>Совпадений с опубликованным графом навыков не найдено.</p>}<ul>{current.requirements.map((item, index) => <li className="saved-item" key={`${item.skill_id}.${index}`}><strong>{current.roadmap.find((step) => step.skill_id === item.skill_id)?.name ?? item.skill_id}</strong><p>{LEVELS[item.level]} · фрагмент вакансии: «{item.evidence}»</p></li>)}</ul><h3>Темы для подготовки</h3><ol>{current.roadmap.map((step) => <li className="saved-item" key={step.skill_id}><strong>{step.name}</strong><p>{step.inferred_prerequisite ? "Предварительная основа для требуемого навыка." : "Навык из вакансии."}</p><p>{step.observation === "not_assessed" ? "Пока не проверяли этот навык — пробел не измерен." : "Есть наблюдения из обучения; они не являются оценкой профессионального уровня."}</p><p>{step.ready ? "Основы позволяют приступить к теме." : "Сначала понадобятся предыдущие основы."}</p></li>)}</ol>{current.selected ? <p role="status">Текущий ориентир обучения.</p> : <button className="primary-button" disabled={busy} onClick={() => void target()}>Выбрать как ориентир</button>}<p><a href="/learning/path">Открыть учебный путь</a></p><details><summary>Удалить анализ</summary><p>Сохранённый текст и анализ этой вакансии будут удалены.</p><button className="text-button" disabled={busy} onClick={() => void remove()}>Удалить эту вакансию</button></details></section>}
    </>}
  </section></main>;
}
