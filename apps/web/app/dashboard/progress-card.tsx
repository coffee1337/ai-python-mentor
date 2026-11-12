"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Achievement = { id: string; title: string; description: string; earned: boolean };
type Progress = {
  xp: number;
  level: number;
  level_title: string;
  next_level_xp: number | null;
  streak_days: number;
  longest_streak: number;
  lessons: number;
  knowledge_checks: number;
  coding_passes: number;
  achievements: Achievement[];
};

export default function ProgressCard() {
  const [progress, setProgress] = useState<Progress | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api<Progress>("/me/progress")
      .then((value) => alive && setProgress(value))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  if (failed) {
    return (
      <p className="product-field-hint" role="status">
        Прогресс временно недоступен — уроки и практика работают.
      </p>
    );
  }
  if (!progress) return <p className="product-field-hint">Считаем прогресс…</p>;

  const earned = progress.achievements.filter((item) => item.earned);

  return (
    <div className="progress-card">
      <div className="progress-card__head">
        <strong>{progress.level_title}</strong>
        <span className="progress-card__xp">{progress.xp} XP</span>
      </div>
      <p className="product-field-hint">
        {progress.next_level_xp
          ? `До следующего уровня: ${Math.max(0, progress.next_level_xp - progress.xp)} XP`
          : "Максимальный уровень пройден"}
      </p>
      <dl className="progress-card__stats">
        <div>
          <dt>Серия</dt>
          <dd>{progress.streak_days} дн.</dd>
        </div>
        <div>
          <dt>Уроки</dt>
          <dd>{progress.lessons}</dd>
        </div>
        <div>
          <dt>Проверки</dt>
          <dd>{progress.knowledge_checks}</dd>
        </div>
        <div>
          <dt>Код</dt>
          <dd>{progress.coding_passes}</dd>
        </div>
      </dl>
      {earned.length > 0 ? (
        <ul className="progress-card__badges" aria-label="Достижения">
          {earned.map((item) => (
            <li key={item.id} title={item.description}>
              {item.title}
            </li>
          ))}
        </ul>
      ) : (
        <p className="product-field-hint">
          Первое достижение — за завершённый урок.
        </p>
      )}
    </div>
  );
}
