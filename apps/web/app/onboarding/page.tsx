"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, OnboardingResponse } from "../lib/api";
import { useUser } from "../lib/use-user";
import ProfileForm from "../components/profile-form";

export default function OnboardingPage() {
  const router = useRouter();
  const { user, loading, error: loadError, reload } = useUser();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api<OnboardingResponse>("/onboarding", { method: "POST", body: JSON.stringify({ display_name: form.get("display_name") || null, experience_level: form.get("experience_level"), target_role: form.get("target_role"), weekly_minutes: Number(form.get("weekly_minutes")), motivation: form.get("motivation") || null }) });
      router.push("/dashboard");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally { setBusy(false); }
  }

  return (
    <main className="auth-shell">
      <a className="brand" href="/">↗ наставник<span className="brand-dot">.</span></a>
      <section className="auth-card onboarding-card">
        <span className="eyebrow">НАСТРОИМ МАРШРУТ</span>
        <h1>Куда вы хотите прийти?</h1>
        <p className="auth-lead">Пара ответов поможет начать с подходящего уровня.</p>
        {loading && <p role="status">Загружаем настройки…</p>}
        {loadError && <div role="alert"><p className="form-error">{loadError}</p><button className="text-button" onClick={() => void reload()}>Повторить загрузку</button></div>}
        {user && <ProfileForm user={user} busy={busy} error={error} onSubmit={submit} submitLabel={user.profile?.onboarding_completed ? "Сохранить настройки" : "Собрать мой маршрут"} />}
      </section>
    </main>
  );
}
