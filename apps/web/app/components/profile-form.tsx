"use client";

import { FormEvent } from "react";
import type { User } from "../lib/api";

export default function ProfileForm({ user, busy, error, onSubmit, submitLabel = "Сохранить" }: {
  user: User;
  busy: boolean;
  error: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  submitLabel?: string;
}) {
  return (
    <form className="settings-form" onSubmit={onSubmit}>
      <fieldset disabled={busy}>
        <label>Как к вам обращаться?<input name="display_name" defaultValue={user.profile?.display_name ?? ""} maxLength={100} autoComplete="given-name" /></label>
        <label>Ваш текущий опыт
          <select name="experience_level" defaultValue={user.profile?.experience_level ?? "beginner"}>
            <option value="beginner">Я начинаю с нуля</option>
            <option value="student">Уже немного пробовал</option>
            <option value="junior">Пишу небольшие программы</option>
          </select>
        </label>
        <label>Цель<input name="target_role" defaultValue={user.goal?.target_role ?? "Python Backend разработчик"} required minLength={2} maxLength={120} /></label>
        <label>Минут в неделю<input type="number" name="weekly_minutes" defaultValue={user.goal?.weekly_minutes ?? 180} required min={15} max={1200} step={1} /></label>
        <label>Что мотивирует вас? <span className="optional">необязательно</span><textarea name="motivation" defaultValue={user.goal?.motivation ?? ""} rows={3} maxLength={2000} /></label>
      </fieldset>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="primary-button form-button" type="submit" disabled={busy}>{busy ? "Сохраняем…" : submitLabel}</button>
    </form>
  );
}
