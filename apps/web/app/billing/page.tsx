"use client";

import { useCallback, useEffect, useState } from "react";
import AppHeader from "../components/app-header";
import { api, errorMessage } from "../lib/api";
import { useUser } from "../lib/use-user";

type Plan = { id: string; name: string; ai_daily_calls: number; checkout_available: boolean };
type Billing = { plan_id: string; status: string; period_end: string | null; entitlements: { ai_daily_calls: number }; usage: { ai_calls_today: number; input_tokens: number | null; output_tokens: number | null; estimated_cost_micro_usd: number | null; cost_is_estimate: boolean } };
export default function BillingPage() {
  const { user, loading, error: userError, reload } = useUser();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [billing, setBilling] = useState<Billing | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadBusy, setLoadBusy] = useState(true);
  const load = useCallback(async () => {
    setLoadBusy(true);
    setError("");
    try { const [catalog, current] = await Promise.all([api<{ plans: Plan[] }>("/billing/plans"), api<Billing>("/me/billing")]); setPlans(catalog.plans); setBilling(current); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setLoadBusy(false); }
  }, []);
  useEffect(() => { if (user) void load(); }, [user, load]);
  async function checkout(planId: string) {
    setBusy(true);
    setError("");
    try { const result = await api<{ checkout_url: string }>("/billing/checkout", { method: "POST", body: JSON.stringify({ plan_id: planId }) }); const url = new URL(result.checkout_url); if (url.protocol !== "https:") throw new Error("Invalid checkout URL"); window.location.assign(url.href); }
    catch (reason) { setError(errorMessage(reason, "Не удалось открыть оплату. Попробуйте позже.")); }
    finally { setBusy(false); }
  }
  return <main className="dashboard-shell"><AppHeader /><section className="dashboard-card"><h1>Тариф и использование AI</h1>
    {(loading || user && loadBusy) && <p role="status">Загружаем данные тарифа…</p>}
    {userError && <div role="alert"><p>{userError}</p><button className="text-button" onClick={() => void reload()}>Повторить</button></div>}
    {error && <div role="alert"><p className="form-error">{error}</p><button className="text-button" disabled={loadBusy} onClick={() => void load()}>Обновить данные</button></div>}
    {billing && <><h2>Текущий тариф: {plans.find((plan) => plan.id === billing.plan_id)?.name ?? billing.plan_id}</h2><p>Статус: {billing.status === "active" ? "Активен" : billing.status === "free" ? "Бесплатный" : "Требует уточнения"}</p>{billing.period_end && <p>Период до {new Date(billing.period_end).toLocaleDateString("ru-RU")}.</p>}<p>AI-вызовов сегодня: {billing.usage.ai_calls_today} из {billing.entitlements.ai_daily_calls}.</p><p className="muted">Токены: вход {billing.usage.input_tokens ?? "нет данных"}, выход {billing.usage.output_tokens ?? "нет данных"}.</p>{billing.usage.estimated_cost_micro_usd !== null && <p className="muted">{billing.usage.cost_is_estimate ? "Оценка расходов" : "Расходы"}: ${(billing.usage.estimated_cost_micro_usd / 1000000).toFixed(4)}. Это расход AI, а не цена тарифа.</p>}</>}
    <div className="product-list">{plans.map((plan) => <article className="saved-item" key={plan.id}><h2>{plan.name}</h2><p>{plan.ai_daily_calls} AI-вызовов в день</p>{plan.id === billing?.plan_id ? <p>Ваш текущий тариф</p> : plan.checkout_available ? <button className="primary-button" disabled={busy} onClick={() => void checkout(plan.id)}>{busy ? "Открываем оплату…" : "Перейти к оплате"}</button> : <p className="muted">Оплата пока недоступна. Цена и условия появятся в подключённой платёжной форме.</p>}</article>)}</div>
    {!loadBusy && user && plans.length === 0 && !error && <p>Тарифы пока не опубликованы.</p>}
  </section></main>;
}
