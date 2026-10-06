"use client";

import AppHeader from "../../components/app-header";
import { useUser } from "../../lib/use-user";
import ReviewToday from "../review-today";

export default function ReviewsPage() {
  const { user, loading, error, reload } = useUser(true);

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="product-page study-page">
        <header className="page-heading">
          <div>
            <p className="page-kicker">Сохранить изученное</p>
            <h1>Ваши повторения</h1>
            <p className="page-subtitle">
              Короткие вопросы по знакомым темам. Возвращайтесь к ним в своём
              темпе, чтобы увидеть, что удалось вспомнить после паузы.
            </p>
          </div>
          <div className="product-action-row">
            <a className="button-secondary" href="/learning/progress">
              Мой прогресс
            </a>
            <a className="button-secondary" href="/learning">
              Текущий урок
            </a>
          </div>
        </header>

        {loading && (
          <p className="panel product-loading" role="status">
            Готовим ваше пространство повторений…
          </p>
        )}
        {error && (
          <div className="status-message product-error" role="alert">
            <p>{error}</p>
            <button
              className="button-secondary"
              type="button"
              disabled={loading}
              onClick={() => void reload()}
            >
              Повторить загрузку
            </button>
          </div>
        )}
        {user && (
          <>
            <div className="panel study-reviews-panel">
              <ReviewToday />
            </div>
            <section className="panel" aria-labelledby="reviews-next-title">
              <h2 id="reviews-next-title">Что дальше</h2>
              <p className="product-section-intro">
                Ответ на повторении помогает подобрать следующую дату
                возвращения к теме. Новые уроки и их проверки остаются
                отдельной частью обучения.
              </p>
              <div className="product-action-row">
                <a className="button" href="/learning">
                  Продолжить обучение →
                </a>
                <a className="button-secondary" href="/learning/path">
                  Выбрать урок в программе
                </a>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
