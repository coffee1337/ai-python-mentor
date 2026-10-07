<div align="center">

# 🧠 AI Python Mentor

### AI-powered platform for learning Python and backend development

**FastAPI · Next.js · PostgreSQL · RAG · Docker · AI/LLM**

Платформа обучения Python и backend-разработке с персонализированным учебным планом, практическими заданиями, AI-наставником и отслеживанием прогресса.

</div>

---

## ✨ Overview

AI Python Mentor — full-stack приложение для изучения Python с нуля до backend-разработки.

Платформа объединяет:

- структурированную программу обучения;
- практические Python-задания;
- AI-наставника;
- персональный roadmap;
- систему прогресса и повторений;
- анализ вакансий и skill gaps;
- проектную практику;
- Telegram-интеграцию.

Проект построен как production-oriented система с отдельными backend/frontend слоями, PostgreSQL, миграциями, фоновой обработкой задач, CI и изолированной архитектурой исполнения пользовательского Python-кода.

---

## 🚀 Key Features

### 🎓 Learning Platform

- 90 учебных навыков и уроков;
- обучение от Python basics до backend;
- knowledge checks и quiz;
- практические задания;
- система подсказок;
- spaced repetition;
- персонализированный learning roadmap;
- отслеживание прогресса и mastery.

### 🤖 AI Tutor

- AI-чат с учебным контекстом;
- локальный RAG по актуальной версии урока;
- разбор ошибок и пользовательского кода;
- AI-feedback для письменных заданий;
- ограничение AI usage;
- учёт использования и стоимости AI-вызовов.

### 💻 Python Practice

Каждое практическое задание использует контракт:

```python
def solve(payload):
    ...
```

Система поддерживает:

- публичные примеры;
- скрытые тесты;
- сохранение решений;
- историю попыток;
- асинхронную постановку выполнения в очередь.

Исполнение пользовательского кода вынесено за пределы основного API и проектируется как отдельный защищённый Runner.

---

## 🏗 Architecture

```text
                        ┌──────────────────┐
                        │     Browser      │
                        └────────┬─────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │     Next.js      │
                        │     Frontend     │
                        └────────┬─────────┘
                                 │
                                 ▼
┌───────────────┐       ┌──────────────────┐       ┌─────────────────┐
│   Telegram    │──────▶│     FastAPI      │◀─────▶│   PostgreSQL    │
└───────────────┘       │       API        │       └─────────────────┘
                        └────────┬─────────┘
                                 │
                 ┌───────────────┼────────────────┐
                 │               │                │
                 ▼               ▼                ▼
        ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
        │  AI Gateway  │ │ Background   │ │ Python Runner│
        │    + RAG     │ │   Workers    │ │  (isolated)  │
        └──────────────┘ └──────────────┘ └──────────────┘
```

Основное приложение организовано как модульный монолит.

Отдельными процессами могут работать:

- notification dispatcher;
- execution dispatcher;
- Python Runner;
- внешние email / Telegram / billing adapters.

---

## 🛠 Tech Stack

### Backend

- Python 3.12
- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL
- Pydantic
- Argon2
- AsyncIO

### Frontend

- Next.js 15
- React 19
- TypeScript

### AI

- LLM Gateway
- Retrieval-Augmented Generation
- local knowledge index
- usage quotas
- token / cost accounting

### Infrastructure

- Docker
- Docker Compose
- GitHub Actions
- background workers
- PostgreSQL migrations

### Integrations

- Telegram Bot API
- Email delivery adapter
- Billing adapter
- AI providers

---

## 🔐 Authentication & Security

В приложении реализованы:

- cookie-based sessions;
- Argon2 password hashing;
- CSRF protection;
- email confirmation;
- password reset;
- session revocation;
- account export;
- account deletion;
- audit logging для административных операций.

Production-конфигурация требует HTTPS и secure cookies.

```env
APP_ENV=production
COOKIE_SECURE=true
```

Секреты не должны храниться в Git-репозитории.

---

## 🧠 RAG

AI-наставник использует Retrieval-Augmented Generation для получения контекста из учебных материалов.

Knowledge base строится на основе immutable snapshots опубликованных уроков.

```bash
cd apps/api

python -m app.knowledge_base
```

Это позволяет AI работать с конкретной версией учебного материала, которую изучает пользователь.

---

## 📊 Learning Model

Платформа разделяет несколько показателей прогресса:

```text
Knowledge
Practice
Independence
Retention
```

Результат обучения не определяется только количеством правильных ответов.

Система учитывает:

- знания;
- практическое применение;
- самостоятельность;
- сохранение знаний со временем.

---

## 💼 Career Features

Платформа может анализировать текст вакансии и выделять:

- требования;
- необходимые технологии;
- подтверждающие фрагменты вакансии;
- skill gaps пользователя.

На основе выбранной вакансии learning roadmap может перестраиваться под конкретную карьерную цель.

---

## 📦 Project Practice

В платформу входят шаблоны проектов для портфолио.

Для каждого проекта поддерживаются:

- milestones;
- история артефактов;
- проверка комплектности;
- публикация проекта в портфолио.

---

## ⚡ Quick Start

### Requirements

Для локальной разработки:

```text
Python 3.12
Node.js 22
```

PostgreSQL рекомендуется, но для локального запуска можно использовать SQLite.

---

## 🪟 Windows

### Backend

```powershell
git clone https://github.com/Coffee1337/ai-python-mentor.git
cd ai-python-mentor

powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\start-api.ps1 `
  -UseSqlite
```

Backend:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

Health check:

```text
http://127.0.0.1:8000/ready
```

### Frontend

В новом терминале:

```powershell
cd ai-python-mentor

powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\start-web.ps1
```

Откройте:

```text
http://localhost:3000
```

---

## 🐧 Linux / macOS

### Backend

```bash
cd apps/api

python3.12 -m venv .venv

.venv/bin/python -m pip install -r requirements.lock

.venv/bin/python ../../scripts/local-api.py --use-sqlite
```

### Frontend

```bash
cd apps/web

npm ci

API_INTERNAL_URL=http://127.0.0.1:8000 \
NEXT_PUBLIC_API_URL=/api \
npm run dev
```

---

## 🐳 Docker

Создайте конфигурацию:

```bash
cp .env.example .env
```

Запустите PostgreSQL:

```bash
docker compose up -d db
```

Примените миграции:

```bash
docker compose run --rm api alembic upgrade head
```

Запустите приложение:

```bash
docker compose up -d api web
```

После запуска:

```text
Frontend
http://localhost:3000

API
http://localhost:8000

Swagger
http://localhost:8000/docs
```

---

## ⚙️ Configuration

Пример конфигурации находится в:

```text
.env.example
```

Основные группы настроек:

```text
Database
AI Gateway
Email
Telegram
Billing
Runner
Security
```

Пример AI-конфигурации:

```env
AI_GATEWAY_URL=
AI_GATEWAY_MODEL=
AI_GATEWAY_API_KEY=
```

При отсутствии AI Gateway основная учебная система продолжает работать, а AI-функции становятся недоступными.

---

## 🧪 Testing

Backend:

```bash
cd apps/api

python -m pytest -q
```

PostgreSQL-specific tests:

```bash
RUN_POSTGRES_TESTS=1 \
python -m pytest -q tests/test_postgres_specific.py
```

Проверка миграций:

```bash
alembic check
```

Frontend:

```bash
cd apps/web

npm run lint
npm run build
```

Runner tests:

```bash
python -m unittest discover -s apps/runner/tests -v
```

---

## 🔄 CI

GitHub Actions проверяет:

- backend tests;
- PostgreSQL migrations;
- PostgreSQL-specific tests;
- frontend types;
- frontend build;
- worker logic;
- Windows native startup;
- browser UI flows.

Отдельные проверки выполняются для Windows без Docker.

---

## 🖥 Windows Native Development

Для Windows предусмотрены launcher-скрипты, которые проверяют окружение перед запуском приложения.

В частности проверяются:

- версия Python;
- Node.js;
- установка dependencies;
- доступность базы;
- Alembic migrations;
- запуск FastAPI;
- запуск Next.js;
- регистрация и cookie session;
- сохранение локальных данных.

Это позволяет запускать development environment без Docker.

---

## 🔒 Python Code Execution

Пользовательский Python-код **не выполняется внутри основного API**.

Архитектура предусматривает отдельный execution host.

Для production Runner предполагаются:

- Linux host;
- cgroups v2;
- isolated containers / sandbox;
- resource limits;
- seccomp / AppArmor;
- user namespaces;
- mTLS;
- отдельный execution dispatcher.

По умолчанию выполнение пользовательского кода отключено.

Подробнее:

```text
docs/runner-deployment.md
docs/runner-protocol.md
docs/runner-security-review.md
```

---

## 📂 Project Structure

```text
ai-python-mentor/
│
├── apps/
│   ├── api/             # FastAPI backend
│   ├── web/             # Next.js frontend
│   └── runner/          # isolated Python execution
│
├── docs/                # architecture / deployment docs
├── scripts/             # development and maintenance scripts
├── .github/
│   └── workflows/       # CI
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 📚 Documentation

Дополнительная техническая документация находится в `docs/`.

Особенно:

```text
docs/runner-deployment.md
docs/runner-protocol.md
docs/runner-security-review.md
docs/backup.md
```

Статус реализованных и запланированных компонентов:

```text
UNIMPLEMENTED_STAGES.md
```

---

## 🎯 Project Goals

Проект создаётся как практика разработки сложной full-stack системы с акцентом на:

- backend architecture;
- reliable data processing;
- AI integration;
- security;
- infrastructure;
- testing;
- observability;
- scalable application design.

---

## 👨‍💻 Author

**Egor Trefilov / Coffee1337**

GitHub:  
https://github.com/Coffee1337

Portfolio:  
https://coffee1337.github.io

---

<div align="center">

Built with Python, FastAPI, PostgreSQL, Next.js and AI.

</div>
