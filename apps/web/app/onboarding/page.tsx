"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, OnboardingResponse } from "../lib/api";

const levels = [["beginner", "Я начинаю с нуля"], ["student", "Уже немного пробовал"], ["junior", "Пишу небольшие программы"]];

export default function OnboardingPage() {
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [level, setLevel] = useState("beginner");
  const [role, setRole] = useState("Python Backend разработчик");
  const [minutes, setMinutes] = useState("180");
  const [motivation, setMotivation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api<OnboardingResponse>("/onboarding").then((result) => { if (result.completed) router.replace("/dashboard"); }).catch(() => router.replace("/auth")); }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try { await api<OnboardingResponse>("/onboarding", { method: "POST", body: JSON.stringify({ display_name: displayName || null, experience_level: level, target_role: role, weekly_minutes: Number(minutes), motivation: motivation || null }) }); router.push("/dashboard"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось сохранить настройки"); }
    finally { setBusy(false); }
  }

  return <main className="auth-shell"><a className="brand" href="/">↗ наставник<span className="brand-dot">.</span></a><section className="auth-card onboarding-card"><span className="eyebrow"><i /> НАСТРОИМ МАРШРУТ</span><h1>Куда вы хотите прийти?</h1><p className="auth-lead">Пара ответов поможет начать с подходящего уровня — без лишней теории.</p><form onSubmit={submit}><label>Как к вам обращаться?<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={100} placeholder="Например, Анна" /></label><fieldset><legend>Ваш текущий опыт</legend>{levels.map(([value, label]) => <label className="choice" key={value}><input type="radio" name="level" value={value} checked={level === value} onChange={() => setLevel(value)} />{label}</label>)}</fieldset><label>Цель<input value={role} onChange={(event) => setRole(event.target.value)} required maxLength={120} /></label><label>Сколько времени в неделю?<select value={minutes} onChange={(event) => setMinutes(event.target.value)}><option value="90">Около 1,5 часа</option><option value="180">Около 3 часов</option><option value="300">Около 5 часов</option><option value="600">Больше 10 часов</option></select></label><label>Что мотивирует вас? <span className="optional">необязательно</span><textarea value={motivation} onChange={(event) => setMotivation(event.target.value)} rows={3} maxLength={2000} /></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="primary-button form-button" disabled={busy}>{busy ? "Сохраняем…" : "Собрать мой маршрут"}<span>↗</span></button></form></section></main>;
}
