---
name: backend-implementation
description: Workflow реализации безопасных backend фич.
---

# backend-implementation

Проследи API → домен → БД и текущие соглашения. Сохраняй modular monolith. Валидируй входы и ownership. AI вызовы — через gateway с timeout/retry/fallback/usage. Structured output валидируй; ошибки контролируй. Изменения обучения связывай с evidence. Миграции должны учитывать совместимость и rollback. Запусти релевантные проверки.

Границы ролей: контракты и схемы — api-designer, бэкенд-реализация — implementer, инфраструктура и бэкапы — devops. Не бери на implementer инфраструктурные решения без согласования с devops и не проектируй API в обход architect.

Инвариант mentor usage: каждый mentor POST использует `generate_with_usage` и создаёт ровно одну запись `AIUsageLedger`, включая gateway error и повтор из cache. `chars` записываются всегда; `tokens` — только если провайдер вернул точное целое число. Не логируй secrets; сохраняй существующие rate limit и idempotency.
