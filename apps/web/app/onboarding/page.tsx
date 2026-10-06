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
    const experience = form.get("experience_level");
    setBusy(true);
    setError("");
    try {
      await api<OnboardingResponse>("/onboarding", {
        method: "POST",
        body: JSON.stringify({
          display_name: form.get("display_name") || null,
          experience_level: experience,
          target_role: form.get("target_role"),
          weekly_minutes: Number(form.get("weekly_minutes")),
          motivation: form.get("motivation") || null,
        }),
      });
      router.push(experience === "beginner" ? "/learning" : "/dashboard");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="entry-shell onboarding-shell">
      <header className="entry-header">
        <a className="brand" href="/">
          наставник<span className="brand-dot">.</span>
        </a>
        <a href="/dashboard">В кабинет</a>
      </header>
      <div className="onboarding-layout">
        <aside className="onboarding-guide">
          <span className="page-kicker">Python → Backend</span>
          <h1 className="page-heading">Настроим обучение под вас</h1>
          <p className="page-subtitle">
            Не нужно знать термины или уметь писать код. Выберите свой опыт и
            удобный темп — начнём с подходящего шага.
          </p>
          <div className="panel onboarding-roadmap">
            <h2 className="panel-heading">К чему идём</h2>
            <ol className="entry-course-steps">
              <li>
                <span>1</span>
                <div>
                  <strong>Понять основы Python</strong>
                  <p>
                    Что такое код, как работают переменные, условия и функции.
                  </p>
                </div>
              </li>
              <li>
                <span>2</span>
                <div>
                  <strong>Научиться работать с данными</strong>
                  <p>
                    Читать и изменять данные, искать ошибки, проверять
                    программы.
                  </p>
                </div>
              </li>
              <li>
                <span>3</span>
                <div>
                  <strong>Разобраться в Backend</strong>
                  <p>
                    Как сервер отвечает сайту, что такое API и как хранить
                    данные.
                  </p>
                </div>
              </li>
            </ol>
            <p className="entry-note">
              Backend — часть приложения на сервере. Например, она сохраняет
              аккаунт и возвращает список задач.
            </p>
          </div>
          <p className="entry-note">
            В уроках есть объяснение и пример, затем небольшое задание.
            AI-наставник помогает разобрать непонятный шаг; проверка задания
            сохраняет ваш результат.
          </p>
        </aside>
        <section
          className="panel onboarding-form-panel"
          aria-labelledby="onboarding-settings-heading"
        >
          <div className="entry-panel-heading">
            <span className="badge">Настройки обучения</span>
            <h2 id="onboarding-settings-heading" className="panel-heading">
              Расскажите о себе
            </h2>
            <p className="page-subtitle">
              Все настройки можно изменить в личном кабинете.
            </p>
          </div>
          {loading && (
            <p className="status-message" role="status">
              Загружаем настройки…
            </p>
          )}
          {loadError && (
            <div className="status-message" role="alert">
              <p>{loadError}</p>
              <button
                className="button button-secondary"
                onClick={() => void reload()}
              >
                Повторить загрузку
              </button>
            </div>
          )}
          {user && (
            <ProfileForm
              key={user.id}
              user={user}
              busy={busy}
              error={error}
              onSubmit={submit}
              submitLabel={
                user.profile?.onboarding_completed
                  ? "Сохранить и продолжить"
                  : "Начать обучение"
              }
            />
          )}
        </section>
      </div>
    </main>
  );
}
