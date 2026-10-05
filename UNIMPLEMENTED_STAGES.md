# Статус реализации

Обновлено 5 октября 2026 года. Состояние кода, не заявление о проверенном production deployment.

Основные backend-контуры Python MVP реализованы: account recovery/privacy, обучение и evidence, 90 уроков и заданий, версии/подсказки/reviews/mistake signals, AI quotas/RAG/планы и generated attempts, вакансии, проекты/portfolio, billing entitlements/webhooks, Telegram/email outbox и tutor, admin/readiness, durable execution jobs и отдельный worker.

## Требует настройки конкретной установки

- AI Gateway и, опционально, paid embeddings: endpoint/model/key и цены конкретной модели. Нет доступа к реальным ключам провайдеров.
- Email и платёжный провайдер: provider-neutral adapters реализованы; контракт adapter-а в README. Нужны выбранный провайдер, credentials, регистрация webhook и проверка реальной доставки/оплаты.
- Telegram: регистрация bot webhook и запуск outbox dispatcher. Реальные сообщения не отправлялись при разработке.
- Runner: проверка целевого Linux host, runsc/seccomp/AppArmor/userns/cgroups, сертификаты и их ротация, reviewed attestation и independent reaper. Без этого исполнение fail-closed. Unit tests не заменяют escape/abuse/cleanup проверки на host.
- Production ingress/TLS, secret mounts, monitoring alerts и реальный backup restore drill. Runbooks и readiness реализованы; развёртывание не выполнялось.

## Осознанные границы

- URL вакансии сохраняется как источник, но сервер не делает произвольный fetch URL. Анализируется вставленный текст, требования сопровождаются точными фрагментами. Правила извлечения — эвристика, не гарантия полноты.
- Проектные milestone-артефакты проверяются на наличие требуемых разделов. Корректность произвольного репозитория, FastAPI-сервера или SQL-инфраструктуры не подтверждается.
- Свободные письменные ответы и AI-разбор рекомендательные. Только доверенные authored tests/graded sources создают acquisition evidence; reviews изменяют retention.
- Mastery/retention intervals — объяснимые продуктовые эвристики, не откалиброванная вероятность квалификации или трудоустройства.
- C++, ML, React live IDE, full repository execution, native apps, социальные функции, сертификаты и Kubernetes остаются вне Python MVP по разделу 90 спецификации.
