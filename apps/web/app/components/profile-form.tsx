"use client";

import { FormEvent, useState } from "react";
import type { User } from "../lib/api";

const EXPERIENCE_OPTIONS = [
  {
    value: "beginner",
    title: "С нуля — ещё не писал код",
    description: "Начнём с того, что такое программа. Диагностика не нужна.",
  },
  {
    value: "student",
    title: "Уже немного пробовал",
    description:
      "Знаком с переменными или простыми программами. Можно проверить основы.",
  },
  {
    value: "junior",
    title: "Пишу небольшие программы",
    description: "Хочу закрепить Python и перейти к серверной разработке.",
  },
];

export default function ProfileForm({
  user,
  busy,
  error,
  onSubmit,
  submitLabel = "Сохранить настройки",
}: {
  user: User;
  busy: boolean;
  error: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  submitLabel?: string;
}) {
  const [experience, setExperience] = useState(
    user.profile?.experience_level ?? "beginner",
  );
  const [weeklyMinutes, setWeeklyMinutes] = useState(
    String(user.goal?.weekly_minutes ?? 180),
  );

  return (
    <form className="settings-form profile-form" onSubmit={onSubmit}>
      <fieldset disabled={busy} className="profile-fields">
        <label htmlFor="profile-name">
          Как к вам обращаться? <span className="optional">необязательно</span>
          <input
            id="profile-name"
            name="display_name"
            defaultValue={user.profile?.display_name ?? ""}
            maxLength={100}
            autoComplete="given-name"
            placeholder="Ваше имя"
          />
        </label>
        <fieldset className="experience-fieldset">
          <legend>С какого места начнём?</legend>
          <div className="experience-options">
            {EXPERIENCE_OPTIONS.map((option) => (
              <label
                className="experience-option"
                key={option.value}
                data-selected={experience === option.value}
              >
                <input
                  type="radio"
                  name="experience_level"
                  value={option.value}
                  checked={experience === option.value}
                  onChange={() => setExperience(option.value)}
                  required
                />
                <span>
                  <strong>{option.title}</strong>
                  <small>{option.description}</small>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="profile-field-grid">
          <label htmlFor="profile-goal">
            Чему хотите научиться?
            <input
              id="profile-goal"
              name="target_role"
              defaultValue={
                user.goal?.target_role ?? "Python Backend разработчик"
              }
              required
              minLength={2}
              maxLength={120}
              aria-describedby="profile-goal-help"
            />
            <span className="field-help" id="profile-goal-help">
              Текущий курс: Python → серверные приложения. Цель помогает выбрать
              приоритеты.
            </span>
          </label>
          <label htmlFor="profile-time">
            Сколько времени есть в неделю?
            <div className="time-input">
              <input
                id="profile-time"
                type="number"
                name="weekly_minutes"
                value={weeklyMinutes}
                onChange={(event) => setWeeklyMinutes(event.target.value)}
                required
                min={15}
                max={1200}
                step={1}
                aria-describedby="profile-time-help"
              />
              <span>минут</span>
            </div>
            <span className="field-help" id="profile-time-help">
              Например, 180 минут — три занятия по часу. Темп можно изменить
              позже.
            </span>
          </label>
        </div>
        <label htmlFor="profile-motivation">
          Для чего вам программирование?{" "}
          <span className="optional">необязательно</span>
          <textarea
            id="profile-motivation"
            name="motivation"
            defaultValue={user.goal?.motivation ?? ""}
            rows={3}
            maxLength={2000}
            placeholder="Например, хочу сменить профессию или сделать свой сервис"
          />
        </label>
      </fieldset>
      {error && (
        <p className="status-message form-error" role="alert">
          {error}
        </p>
      )}
      <div className="profile-form-footer">
        <p className="field-help">
          {experience === "beginner"
            ? "После сохранения можно сразу открыть первый урок. Вступительного теста нет."
            : "Диагностика необязательна: можно сразу учиться и проверять знания по ходу."}
        </p>
        <button className="button" type="submit" disabled={busy}>
          {busy ? "Сохраняем…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
