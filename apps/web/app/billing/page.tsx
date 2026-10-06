"use client";

import { useCallback, useEffect, useState } from "react";
import AppHeader from "../components/app-header";
import { api, errorMessage } from "../lib/api";
import { useUser } from "../lib/use-user";

type Plan = {
  id: string;
  name: string;
  ai_daily_calls: number;
  checkout_available: boolean;
};
type Billing = {
  plan_id: string;
  status: string;
  period_end: string | null;
  entitlements: { ai_daily_calls: number };
  usage: {
    ai_calls_today: number;
    input_tokens: number | null;
    output_tokens: number | null;
    estimated_cost_micro_usd: number | null;
    cost_is_estimate: boolean;
  };
};

export default function BillingPage() {
  const { user, loading, error: userError, reload } = useUser();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [billing, setBilling] = useState<Billing | null>(null);
  const [error, setError] = useState("");
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [loadBusy, setLoadBusy] = useState(true);

  const load = useCallback(async () => {
    setLoadBusy(true);
    setError("");
    try {
      const [catalog, current] = await Promise.all([
        api<{ plans: Plan[] }>("/billing/plans"),
        api<Billing>("/me/billing"),
      ]);
      setPlans(catalog.plans);
      setBilling(current);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoadBusy(false);
    }
  }, []);

  useEffect(() => {
    if (user) void load();
  }, [user, load]);

  async function checkout(planId: string) {
    if (busyPlan) return;
    setBusyPlan(planId);
    setError("");
    try {
      const result = await api<{ checkout_url: string }>("/billing/checkout", {
        method: "POST",
        body: JSON.stringify({ plan_id: planId }),
      });
      const url = new URL(result.checkout_url);
      if (url.protocol !== "https:") throw new Error("Invalid checkout URL");
      window.location.assign(url.href);
    } catch (reason) {
      setError(
        errorMessage(reason, "Не удалось открыть оплату. Попробуйте позже."),
      );
    } finally {
      setBusyPlan(null);
    }
  }

  const currentName =
    plans.find((plan) => plan.id === billing?.plan_id)?.name ??
    billing?.plan_id;
  const remainingCalls = billing
    ? Math.max(
        0,
        billing.entitlements.ai_daily_calls - billing.usage.ai_calls_today,
      )
    : 0;

  return (
    <main className="dashboard-shell">
      <AppHeader />
      <div className="product-page">
        <header className="page-heading">
          <div>
            <p className="page-kicker">Подписка</p>
            <h1>Тариф и AI-наставник</h1>
            <p className="page-subtitle">
              Посмотрите свой дневной лимит и доступные варианты подписки.
            </p>
          </div>
        </header>

        {(loading || (user && loadBusy)) && (
          <div className="panel product-loading" role="status">
            Загружаем тариф и использование…
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
              disabled={loadBusy || !!busyPlan}
              onClick={() => void load()}
            >
              Обновить данные
            </button>
          </div>
        )}

        {user && billing && (
          <>
            <div className="billing-overview-grid">
              <section className="panel billing-current-plan">
                <div className="panel-heading">
                  <p className="page-kicker">Ваш тариф</p>
                  <span className="badge product-badge-positive">
                    {billing.status === "active"
                      ? "Активен"
                      : billing.status === "free"
                        ? "Бесплатный"
                        : "Статус требует уточнения"}
                  </span>
                </div>
                <h2>{currentName}</h2>
                <p>
                  {billing.entitlements.ai_daily_calls} обращений к AI в день
                </p>
                {billing.period_end && (
                  <p className="product-field-hint">
                    Текущий период до{" "}
                    {new Date(billing.period_end).toLocaleDateString("ru-RU")}.
                  </p>
                )}
                <a className="product-inline-link" href="/learning">
                  Перейти к обучению <span aria-hidden="true">→</span>
                </a>
              </section>

              <section
                className="panel billing-usage-panel"
                aria-labelledby="daily-usage-title"
              >
                <div className="panel-heading">
                  <h2 id="daily-usage-title">Использование сегодня</h2>
                  <span className="badge">Дневной лимит</span>
                </div>
                <div className="billing-usage-number">
                  <strong>{billing.usage.ai_calls_today}</strong>
                  <span>
                    из {billing.entitlements.ai_daily_calls} обращений
                  </span>
                </div>
                {billing.entitlements.ai_daily_calls > 0 && (
                  <progress
                    className="billing-usage-progress"
                    value={Math.min(
                      billing.usage.ai_calls_today,
                      billing.entitlements.ai_daily_calls,
                    )}
                    max={billing.entitlements.ai_daily_calls}
                    aria-label="Использовано обращений к AI за сегодня"
                  />
                )}
                <p className="product-field-hint">
                  {remainingCalls > 0
                    ? `Доступно ещё ${remainingCalls} обращений в рамках дневного лимита.`
                    : "Дневной лимит исчерпан. Учебные материалы остаются доступны."}
                </p>
              </section>
            </div>

            <section className="panel billing-ai-explainer">
              <div>
                <p className="page-kicker">Как помогает нейросеть</p>
                <h2>Объяснение именно для вашей ситуации</h2>
              </div>
              <p>
                В уроках уже есть теория и примеры. AI-наставник нужен, когда
                хочется спросить «почему», разобрать свою ошибку или получить
                следующий шаг без готового решения. Он доступен, если на сервере
                настроен AI-сервис.
              </p>
            </section>

            <section aria-labelledby="plans-title">
              <div className="product-section-heading">
                <div>
                  <h2 id="plans-title">Доступные тарифы</h2>
                  <p className="product-section-intro">
                    Окончательная цена и условия отображаются в подключённой
                    платёжной форме.
                  </p>
                </div>
              </div>
              <div className="billing-plan-grid">
                {plans.map((plan) => (
                  <article
                    className={`panel billing-plan-card ${plan.id === billing.plan_id ? "billing-plan-selected" : ""}`}
                    key={plan.id}
                  >
                    <div className="panel-heading">
                      <h3>{plan.name}</h3>
                      {plan.id === billing.plan_id && (
                        <span className="badge product-badge-positive">
                          Ваш тариф
                        </span>
                      )}
                    </div>
                    <p className="billing-plan-limit">
                      <strong>{plan.ai_daily_calls}</strong>
                      <span>AI-обращений / день</span>
                    </p>
                    <p className="product-section-intro">
                      Для вопросов наставнику и персональной помощи в обучении.
                    </p>
                    <div className="billing-plan-action">
                      {plan.id === billing.plan_id ? (
                        <span className="product-current-note">
                          Тариф уже подключён
                        </span>
                      ) : plan.checkout_available ? (
                        <button
                          className="button"
                          disabled={!!busyPlan}
                          onClick={() => void checkout(plan.id)}
                        >
                          {busyPlan === plan.id
                            ? "Открываем оплату…"
                            : "Перейти к оплате"}
                        </button>
                      ) : (
                        <>
                          <button className="button button-secondary" disabled>
                            Оплата пока недоступна
                          </button>
                          <p className="product-field-hint">
                            Платёжная форма для этого тарифа ещё не подключена.
                          </p>
                        </>
                      )}
                    </div>
                  </article>
                ))}
              </div>
              {!loadBusy && plans.length === 0 && !error && (
                <div className="panel empty-state">
                  <h3>Тарифы пока не опубликованы</h3>
                  <p>Когда появятся доступные планы, вы увидите их здесь.</p>
                </div>
              )}
            </section>

            <details className="panel product-disclosure">
              <summary>Техническая статистика AI-запросов</summary>
              <dl className="billing-technical-stats">
                <div>
                  <dt>Входящие токены</dt>
                  <dd>
                    {billing.usage.input_tokens?.toLocaleString("ru-RU") ??
                      "Нет данных"}
                  </dd>
                </div>
                <div>
                  <dt>Исходящие токены</dt>
                  <dd>
                    {billing.usage.output_tokens?.toLocaleString("ru-RU") ??
                      "Нет данных"}
                  </dd>
                </div>
                {billing.usage.estimated_cost_micro_usd !== null && (
                  <div>
                    <dt>
                      {billing.usage.cost_is_estimate
                        ? "Оценка расходов AI"
                        : "Расходы AI"}
                    </dt>
                    <dd>
                      $
                      {(
                        billing.usage.estimated_cost_micro_usd / 1000000
                      ).toFixed(4)}
                    </dd>
                  </div>
                )}
              </dl>
              <p className="product-field-hint">
                Это технические расходы на AI, а не цена вашей подписки.
              </p>
            </details>
          </>
        )}
      </div>
    </main>
  );
}
