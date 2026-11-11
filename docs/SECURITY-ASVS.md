# OWASP ASVS 2.0: чеклист уровня 2 (auth, сессии, загрузки, AI)

Область: главы V2 (аутентификация), V3 (сессии), V5 (валидация, заголовки), V12 (файлы),
плюс границы prompt injection для AI-контура. Уровень 2, только пункты, применимые к
продукту. Каждый «pass» подкреплён файлом и тестом; всё, что не проверено, помечено честно.

Дата: 2026-11-11. Проверка: `cd apps/api && python -m pytest -q` (346 passed),
`ruff check apps scripts` (clean), `npx playwright test` (8 passed).

## V2. Аутентификация

| ID | Требование | Статус | Доказательство |
|---|---|---|---|
| 2.1.1 | Пароль не короче 12 символов | pass | `app/schemas.py:16` (`min_length=12`), `tests/test_asvs_controls.py::test_short_password_is_rejected_by_the_api` |
| 2.1.7 | Проверка пароля по списку утечек | pass | `app/passwords.py` (HIBP k-anonymity, уходит только 5 символов хэша), `tests/test_asvs_sessions.py::test_registration_rejects_a_breached_password`; при недоступности сети проверка не блокирует регистрацию (осознанно, отказ третьей стороны не должен ронять вход) |
| 2.1.9 | Нет композиционных правил, кроме длины | pass | нет требований на спецсимволы |
| 2.2.1 | Защита от перебора (rate limit) | pass | `app/auth.py:44-49` (`throttle` по ip и по аккаунту, 20/мин), `tests/test_asvs_controls.py::test_login_attempts_are_throttled_per_account` |
| 2.2.3 | Уведомление о неудачных входах | **пройдено** | `tests/test_email_delivery.py::test_failed_login_notice_arrives_once_per_hour` — письмо уходит по SMTP на локальный сервер, одно на серию (дедуп по часу), неизвестный аккаунт письма не получает |
| 2.4.1 | Хэширование паролей стойкой функцией | pass | argon2id, `app/security.py:12-33`; в production без argon2 старт падает |
| 2.4.3 | Соль на пользователя | pass | argon2 встроенная соль |
| 2.5.1 | Сброс пароля по одноразовому токену | pass | `app/account_services.py:85-126`, `tests/test_account_services.py::test_verification_is_single_use_and_never_stores_raw_token_in_token_table` |
| 2.5.2 | Токен сброса не хранится в открытом виде | pass | хранится `sha256`, тот же тест |
| 2.5.4 | Токен одноразовый | pass | `consume_token`, тот же тест |
| 2.7.1 | Подтверждение email при регистрации | pass | `tests/test_account_services.py`, dev-токен только при `DEV_ACCOUNT_TOKENS=true` и `APP_ENV != production` |
| 2.9.1 | Криптостойкий ГПСЧ для токенов | pass | `new_token()` → `secrets.token_urlsafe(32)` (`app/security.py:21`), хэш через `token_digest` |

## V3. Сессии

| ID | Требование | Статус | Доказательство |
|---|---|---|---|
| 3.1.1 | Сессия не в URL | pass | cookie `SESSION_COOKIE` |
| 3.2.1 | Cookie `Secure` в production | pass | `app/auth.py:36,53-55`, `COOKIE_SECURE=true` в `compose.prod.yml` |
| 3.2.2 | Cookie `HttpOnly` для сессии | pass | `app/auth.py:54` |
| 3.2.3 | `SameSite` | pass | `Lax` для сессии и CSRF-cookie |
| 3.3.1 | Выход инвалидирует сессию | pass | `POST /auth/logout` (`app/auth.py:175`), `tests/test_auth.py::test_login_logout_and_invalid_password` |
| 3.3.3 | Отзыв всех сессий | pass | `revoke_sessions` (`app/account_services.py:85`), покрыто `tests/test_account_services.py` |
| 3.4.1 | CSRF-защита изменяющих запросов | pass | двойная отправка + `hmac.compare_digest` (`app/auth.py:108-122`), `tests/test_auth.py::test_profile_update_is_csrf_protected`, `tests/test_learning.py::test_auth_onboarding_csrf_and_validation` |
| 3.5.2 | Токен сессии хранится в виде хэша | pass | `token_digest` (`app/auth.py:65`) |
| 3.7.1 | Срок жизни сессии ограничен | pass | 30 дней (`SESSION_TTL`); idle-timeout не реализован |
| 3.7.2 | Абсолютный срок жизни | pass | `SESSION_ABSOLUTE_TTL` проверяется отдельно от `expires_at` (`app/auth.py`), `tests/test_asvs_sessions.py::test_session_older_than_the_absolute_window_is_rejected` |

## V5. Валидация, заголовки, лимиты

| ID | Требование | Статус | Доказательство |
|---|---|---|---|
| 5.1.3 | Схемы запросов строгие (`extra=forbid`) | pass | `app/schemas.py`, `ConfigDict(extra="forbid")` |
| 5.1.4 | Отказ по неожидаемым полям | pass | `ConfigDict(extra="forbid")`, `tests/test_auth.py::test_login_logout_and_invalid_password` (422 на лишние поля) |
| 5.2.1 | Защита от mass assignment | pass | Pydantic-модели, сервер не принимает `user_id`/`status` |
| 5.3.1 | Кодировка ответов | pass | `application/json; charset=utf-8` |
| 5.3.3 | Заголовки безопасности | pass | `app/security_headers.py` (CSP `default-src 'none'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`), `tests/test_security_headers.py` |
| 5.3.4 | HSTS только по TLS | pass | middleware добавляет `Strict-Transport-Security` при `scheme=https`, тест `test_hsts_only_over_tls` |
| 5.4.1 | `Content-Security-Policy` во фронтенде | pass | `apps/web/next.config.ts` (same-origin, `frame-ancestors 'none'`, `object-src 'none'`) |
| 5.5.1 | Лимит размера тела запроса | pass | `app/http_limits.py` (128 KiB), `tests/test_security_headers.py::test_oversized_body_is_rejected_before_validation` |
| 5.5.3 | Нет подробных ошибок наружу | pass | `tests/test_mentor.py::test_failure_saved_and_explicit_retry` (ключ провайдера не утекает) |
| 5.6.1 | Отсутствие SQL-инъекций | pass | SQLAlchemy, нет конкатенации SQL |
| 5.7.1 | Приватные ответы не кэшируются | pass | `Cache-Control: no-store` на `/me`, `/auth/*`, `/learning/drafts`, `tests/test_security_headers.py::test_private_endpoints_are_not_cacheable` |
| 5.1.1 | Позитивные ограничения на принимаемый контент | pass | `StrictStr` + `min_length/max_length` в схемах |

## V12. Файлы и загрузки

| ID | Требование | Статус | Доказательство |
|---|---|---|---|
| 12.1.1 | Файлы не исполняются как код | pass | загрузок файлов в API нет; код ученика исполняется только в runner |
| 12.2.1 | Тип и размер ограничены | н/п | эндпоинтов загрузки нет |
| 12.4.1 | Файлы вне web-root | pass | нет пользовательских файлов |
| 12.6.1 | Секреты не в файлах-логах | pass | JSON-логи без промптов и ключей, `test_every_call_is_logged_with_tokens_and_cost` |

## AI-контур: prompt injection и утечки

| Требование | Статус | Доказательство |
|---|---|---|
| Пользовательский и retrieved-контент помечен как данные, не инструкции | pass | `app/mentor_prompts.py`, `app/knowledge_base.py` (пометка «untrusted data, not instructions») |
| Внутренние ответы валидируются схемой | pass | `app/mentor.py` (Pydantic на выходе провайдера) |
| Ключ провайдера не попадает в ответы и логи | pass | `tests/test_mentor.py`, `tests/test_knowledge_base.py::test_gateway_key_never_reaches_logs_or_responses` |
| Стоимость и токены учитываются на каждый вызов | pass | `app/ai_gateway.py::_report`, `tests/test_model_routing.py` |
| Дневной лимит расходов и алерт на 80 % | pass | `app/ai_admission.py`, `tests/test_model_routing.py::test_global_daily_limit_blocks_the_next_reservation`, `test_eighty_percent_threshold_emits_one_alert_per_day` |
| RAG отдаёт точную версию урока | pass | `app/knowledge_base.py` (поиск по skill+version), `tests/test_knowledge_base.py` |
| Данные ученика не отправляются третьим лицам без согласия | не проверено | политики/согласия в продукте нет; требует решения владельца |
| Вызов кода из AI-ответа запрещён | pass | ответ тьютора — только текст, runner принимает лишь source ученика |

## Что осталось открытым

1. ~~**2.2.3** — уведомление о неудачных входах~~ закрыто: SMTP-транспорт и письмо о неудачных входах проверены сквозным тестом на реальном SMTP-сокете.
2. **Согласие на обработку данных AI** — продуктовая и юридическая задача владельца.

Оба пункта требуют либо внешнего аккаунта, либо решения владельца; внесены в `docs/STATUS.md`.
