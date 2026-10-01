# AI-наставник по программированию — полный Product & Technical Specification

> Версия: 1.0  
> Дата: 30 сентября 2026  
> Назначение: подробное продуктовое и техническое ТЗ для разработки веб-платформы персонального AI-наставника по программированию.

---

## 1. Суть продукта

Продукт — веб-платформа с персональным AI-наставником, который ведёт пользователя от его текущего уровня к конкретной цели. Это не «курс + чат», а адаптивная система обучения, которая знает, что пользователь уже умеет, чего не умеет, какие ошибки совершает, какие ошибки повторяет, что забывает, как решает задачи, сколько подсказок ему нужно и какой стек требуется для его цели или вакансии.

Главная формула продукта:

> **Skill Graph + Student Model + Long-term Memory + Curriculum Engine + Knowledge Base + Practice Environment + Code Execution + AI Tutor + Goal/Vacancy Engine.**

Пользователь может начать с полного нуля, пройти адаптивную диагностику, выбрать направление или загрузить вакансию, получить персональный план, изучать теорию, отвечать на вопросы, писать настоящий код, запускать его в изолированной среде, получать hidden tests, подсказки, code review, выполнять проекты и видеть, как меняется его карта навыков.

В перспективе платформа покрывает Python, Python Backend, JavaScript, TypeScript, React, HTML/CSS, C++, SQL, Git, Docker, Data Analysis, ML, Deep Learning, AI/LLM Engineering, MLOps, алгоритмы и системный дизайн. Но MVP должен быть значительно уже: **Python → Python Backend**.

---

## 2. Какую проблему решает продукт

### 2.1. Одинаковые курсы для разных людей

Обычный курс одинаков для пользователя, который не знает переменных, и пользователя, который уже писал pet-project. Результат — скука у сильного, пробелы у слабого. У нас curriculum динамический: человек проходит только то, что нужно именно ему.

### 2.2. AI слишком легко делает работу вместо ученика

Обычный сценарий: задача → пользователь не знает → вставляет в ChatGPT → копирует решение → считает, что понял. Продукт должен сознательно избегать этого. Цель AI — **максимизировать обучение, а не скорость выдачи готового кода**.

### 2.3. Обычный чат не хранит учебную модель пользователя

Нужна отдельная структурированная память: темы, mastery, ошибки, misconception, количество подсказок, история практики, забывание, проекты, цели и целевые вакансии. История сообщений сама по себе этого не заменяет.

### 2.4. Курсы слабо связаны с реальной карьерной целью

Если человеку нужна вакансия Python Backend, система должна видеть требования вакансии и строить gap analysis: Python 80%, SQL 40%, Docker 10%, FastAPI 50%, testing 25% и т.д. Отсюда строится план.

### 2.5. Теория отделена от практики

Цикл должен быть таким:

```text
Теория
  ↓
Проверка понимания
  ↓
Мини-задача
  ↓
Практика
  ↓
Проект
  ↓
Code review
  ↓
Повторение
  ↓
Проверка без подсказок
```

---

## 3. Позиционирование

Плохой вариант: «Курсы программирования с AI».

Сильнее:

- «Персональный AI-наставник, который помнит твои ошибки и учит именно тому, чего тебе не хватает».
- «Загрузи вакансию — AI проверит твой уровень и построит путь до её требований».
- «AI, который не пишет код вместо тебя, пока ты можешь дойти до решения сам».

Главный продуктовый тезис: **LLM не является продуктом. LLM — один компонент образовательной системы.**

---

## 4. Целевые аудитории

### 4.1. Полный новичок

Не знает терминов, Git, IDE, терминал. Нужны мягкий onboarding, минимум жаргона, маленькие шаги и быстрый первый успех.

### 4.2. Студент

Есть хаотичные знания, часть домашних работ делалась с AI, реальный уровень неизвестен. Нужны диагностика, закрытие пробелов, практика и подготовка к стажировкам/экзаменам.

### 4.3. Junior developer

Пишет код, но не понимает, чего не хватает до следующего уровня. Нужны code review, архитектура, тестирование, production practices и индивидуальный growth plan.

### 4.4. Человек под конкретную вакансию

Один из самых сильных use case: текст вакансии + резюме/GitHub → skill gap → индивидуальный учебный план → mock interview.

### 4.5. Опытный разработчик

Поздний сегмент: большие repository, architecture review, performance, testing, design patterns, system design.

---

## 5. Основные доменные сущности

Система должна быть построена вокруг домена, а не страниц UI.

Основные сущности:

1. User
2. Profile
3. Goal
4. Vacancy
5. Learning Path
6. Skill
7. Skill Edge
8. User Skill / Mastery
9. Skill Evidence
10. Concept
11. Course
12. Module
13. Lesson
14. Knowledge Unit
15. Exercise
16. Submission
17. Test Case
18. Hint
19. Mistake
20. Misconception
21. Assessment
22. Project
23. Project Milestone
24. Repository
25. Code Symbol
26. Code Relation
27. Code Finding
28. Memory Record
29. Learning Session
30. Review Schedule
31. Tutor Thread
32. Tutor Message
33. Subscription
34. Usage Event
35. AI Usage Event

---

## 6. Основной пользовательский путь

### 6.1. Регистрация

Минимум трения: email/password или OAuth. После входа сразу onboarding. Не собирать ненужные данные до появления ценности.

### 6.2. Выбор цели

Примеры:

- научиться программированию с нуля;
- стать Python Backend разработчиком;
- подготовиться к вакансии;
- подтянуть текущий уровень;
- разобраться в своём проекте;
- позже: React, Data Science, ML.

### 6.3. Самооценка

Варианты: полный ноль / основы / делал проекты / работаю. Самооценка — только prior, окончательный уровень определяет диагностика.

### 6.4. Диагностика

Адаптивные вопросы разных типов. Чем увереннее ответы, тем быстрее система поднимает сложность и пропускает очевидные темы.

### 6.5. Построение Learning Path

На входе: цель, диагностика, prerequisites, vacancy requirements. На выходе: индивидуальный roadmap.

### 6.6. Ежедневная работа

Главный экран отвечает на вопрос: **«Что мне делать сегодня?»**. Пользователь получает конечную сессию на 20–60 минут, а не бесконечный каталог уроков.

---

## 7. Skill Graph

Skill Graph — центральная модель знаний.

Пример Python Backend:

```text
Programming Foundations
├── variables
├── data types
├── conditionals
├── loops
├── functions
│   ├── parameters
│   ├── return values
│   ├── scope
│   ├── closures
│   └── decorators

Python Core
├── collections
├── comprehensions
├── exceptions
├── iterators
├── generators
├── context managers
├── typing
└── OOP
    ├── classes
    ├── inheritance
    ├── composition
    ├── protocols
    └── dataclasses

Backend
├── HTTP
├── REST
├── FastAPI
├── validation
├── auth
├── dependency injection
└── background tasks

Database
├── SQL
├── PostgreSQL
├── indexes
├── transactions
├── isolation
└── ORM

Engineering
├── Git
├── testing
├── Docker
├── Linux
├── logging
├── CI/CD
└── architecture
```

Каждый skill имеет ID, название, сложность, prerequisites, важность и теги. Пример:

```json
{
  "id": "python.functions.mutable_default_args",
  "name": "Mutable default arguments",
  "category": "python.functions",
  "difficulty": 0.45,
  "prerequisites": ["python.functions.parameters", "python.mutability"],
  "importance": 0.55,
  "tags": ["python", "functions", "pitfalls"]
}
```

Skill edges хранят отношения prerequisite / related / specialization.

---

## 8. Модель mastery

Нельзя хранить только «Python = 74%». Для навыка нужны разные измерения:

```text
knowledge_score
practice_score
independent_score
retention_score
confidence
evidence_count
last_practiced_at
next_review_at
```

Пример:

```json
{
  "skill": "sql.joins",
  "knowledge": 0.82,
  "practice": 0.61,
  "independent": 0.44,
  "retention": 0.53,
  "confidence": 0.78,
  "evidence_count": 14
}
```

`independent_score` принципиально важен: десять задач с готовыми подсказками не равны десяти задачам, решённым самостоятельно.

Каждое изменение mastery должно быть связано с evidence: quiz, coding task, project, delayed review, interview question, explanation task и т.д. Практическое доказательство обычно сильнее multiple choice.

---

## 9. Адаптивная диагностика

Диагностика не должна быть статическим тестом из 100 вопросов.

Каждый вопрос имеет:

- skill_id;
- difficulty;
- expected_time;
- prerequisites;
- answer_type;
- diagnostic value.

Если пользователь уверенно решает beginner loops → дать intermediate. Если снова правильно → edge case. Если ошибка → диагностировать misconception и при необходимости опуститься к prerequisite.

Типы вопросов:

- multiple choice;
- что выведет код;
- короткий ответ;
- исправить баг;
- написать функцию;
- объяснить концепцию своими словами;
- прочитать чужой код;
- оценить сложность;
- небольшой refactor.

Цель — за минимальное число действий построить достаточно точную карту навыков.

---

## 10. Curriculum Engine

Это модуль, который каждый день решает: **что пользователь должен изучать следующим?**

Вход:

- цель;
- target skills;
- current mastery;
- prerequisites;
- ошибки и misconception;
- forgetting risk;
- доступное время;
- история обучения;
- текущие проекты;
- vacancy requirements.

Упрощённая модель приоритета:

```text
priority =
  target_importance
  × skill_gap
  × prerequisite_readiness
  × forgetting_factor
  × goal_relevance
```

Система может чередовать новую тему, повторение и практику, а не идти по фиксированному линейному курсу.

---

## 11. Vacancy → индивидуальный roadmap

Pipeline:

```text
Vacancy text / URL
   ↓
Requirement extractor
   ↓
Normalized requirements
   ↓
Mapping to Skill Graph
   ↓
Target Skill Profile
   ↓
Compare with User Skill Profile
   ↓
Gap Analysis
   ↓
Personal Learning Path
```

Не достаточно вытащить keywords. Нужен уровень требования и evidence из текста вакансии.

Пользователь получает два профиля: «требуется» и «умею сейчас», затем порядок обучения по gap.

Например:

```text
Требования     Пользователь
Python  90%    78%
FastAPI 80%    52%
SQL     80%    41%
Docker  60%    12%
Redis   55%     5%
Testing 70%    29%
CI/CD   50%     8%
```

Проценты — внутренняя ориентировочная шкала, не абсолютная истина и не «вероятность получить работу».

---

## 12. Learning Session

Пользователь должен видеть конечную сессию:

```text
Сегодня: 40 минут

1. Повторить SQL JOIN — 8 мин
2. FastAPI Dependencies — 12 мин
3. Практика — 15 мин
4. Итоговый вопрос — 5 мин
```

Это психологически проще, чем «продолжить большой курс».

Структура урока:

1. зачем тема нужна;
2. prerequisites;
3. короткое объяснение;
4. пример;
5. checkpoint;
6. misconception check;
7. мини-практика;
8. вывод;
9. review scheduling.

---

## 13. Система подсказок

Для каждой coding-задачи должно быть несколько уровней помощи:

```text
Hint 0 — без помощи
Hint 1 — направление
Hint 2 — нужная концепция
Hint 3 — конкретный следующий шаг
Hint 4 — псевдокод
Hint 5 — частичное решение
Solution — полное решение
```

Использование подсказок влияет на independent mastery. Если пользователь посмотрел solution, задача не считается доказательством самостоятельного владения навыком. Позже система даёт похожую задачу без подсказки.

---

## 14. Practice Engine

Форматы практики:

- predict output;
- fill code;
- implement function;
- debug;
- refactor;
- написать tests;
- SQL query;
- спроектировать API;
- объяснить чужой код;
- mini project;
- architecture decision.

Практика должна быть тематически интересной. Пользователь может указать интересы: игры, финансы, крипта, спорт. Тогда одна и та же концепция оборачивается в разные сценарии, но образовательное ядро не меняется.

---

## 15. Project System

Путь Python Backend может содержать проекты:

1. CLI expense tracker;
2. простой HTTP client;
3. CRUD FastAPI;
4. auth service;
5. PostgreSQL application;
6. Redis cache;
7. background jobs;
8. Dockerized service;
9. финальный production-style backend.

Большой проект делится на milestones: требования → схема данных → endpoints → validation → tests → Docker → refactor.

После проекта можно построить portfolio evidence page: stack, demonstrated skills, tests, GitHub и краткое объяснение пользователя.


---

# 16. Knowledge Base и RAG

Собственную нейросеть обучать на старте не нужно. Знания хранятся отдельно от LLM.

Источники knowledge base:

- собственные учебные материалы;
- официальная документация;
- curated examples;
- типичные ошибки;
- наборы задач;
- project specs;
- rubrics;
- проверенные объяснения.

Pipeline:

```text
Content authoring
  ↓
Normalization
  ↓
Chunking
  ↓
Metadata tagging
  ↓
Embeddings
  ↓
PostgreSQL + pgvector
```

При запросе:

```text
User question
  ↓
Intent/skill detection
  ↓
Metadata-filtered retrieval
  ↓
Vector / hybrid search
  ↓
Optional rerank
  ↓
Top relevant knowledge
  ↓
Tutor prompt
```

Пример metadata chunk:

```json
{
  "course": "python_backend",
  "module": "python_functions",
  "skill_ids": ["python.functions.parameters"],
  "level": "beginner",
  "content_type": "theory",
  "language": "ru",
  "source_version": "1.3"
}
```

На маленькой базе можно начать с exact vector search. При росте pgvector поддерживает HNSW и IVFFlat. Полезно сочетать semantic search с metadata filters и full-text search.

Не надо отправлять модели весь курс. Отправляются только релевантные фрагменты.

---

# 17. Long-term Memory: как реализовать «ИИ помнит всё»

«Помнить всё» не означает каждый раз отправлять в LLM всю историю сообщений. Это было бы дорого и ненадёжно.

Нужны несколько типов памяти.

## 17.1. Profile Memory

Стабильные данные:

- цель;
- опыт;
- выбранный стек;
- язык;
- доступное время;
- интересы;
- предпочтительный стиль объяснений;
- target vacancy.

## 17.2. Skill Memory

Структурированное состояние mastery по каждому skill.

## 17.3. Mistake Memory

Пример:

```json
{
  "skill_id": "python.functions.mutable_defaults",
  "mistake_type": "mutable_default_argument",
  "description": "Использовал [] как default argument",
  "first_seen_at": "...",
  "last_seen_at": "...",
  "count": 3,
  "resolved": false
}
```

## 17.4. Misconception Memory

Нужно различать механическую ошибку и неправильную mental model.

Ошибка:

> забыл двоеточие.

Misconception:

> считает, что default list создаётся заново на каждый вызов функции.

Именно misconception важнее для обучения.

## 17.5. Interaction Summary

После длинной сессии создаётся compact summary:

```text
Изучал SQL JOIN.
INNER JOIN понимает уверенно.
LEFT JOIN путает в случаях NULL.
Потребовалось две подсказки.
Назначить повтор через 2 дня.
```

## 17.6. Behavioral Memory

Наблюдаем, как пользователь реально учится:

- лучше ли после примера;
- лучше ли после самостоятельной практики;
- склонен ли сразу просить solution;
- часто ли торопится;
- насколько правильно оценивает собственную уверенность.

Не нужно слепо хранить ярлык «визуал/аудиал». Лучше опираться на реальные результаты.

---

# 18. Spaced Repetition и забывание

Для каждого skill/concept хранится `next_review_at`.

Простейшая начальная схема:

- incorrect → повтор завтра;
- hard → через 2 дня;
- correct with hint → через 3–4 дня;
- correct independently → через 7 дней;
- repeated success → 14 / 30 / 60 дней.

Позже алгоритм можно заменить на статистическую модель забывания.

Daily plan должен смешивать новую тему и review. Если пользователь давно не практиковал важный навык, система возвращает его в план.

---

# 19. Tutor Engine

Tutor — orchestrator, а не просто один system prompt.

На каждый запрос создаётся context packet:

```json
{
  "goal": "Python Backend Junior",
  "current_topic": "SQL JOIN",
  "mastery": {},
  "recent_mistakes": [],
  "recurring_mistakes": [],
  "current_exercise": {},
  "retrieved_knowledge": [],
  "hint_level": 1,
  "tutor_mode": "socratic",
  "allowed_behavior": "hint_not_solution"
}
```

Режимы Tutor:

- Teach — объяснение новой темы;
- Socratic — наводящие вопросы;
- Hint — минимальная помощь;
- Debug Coach — помогает найти ошибку;
- Review — code review;
- Examiner — проверяет без помощи;
- Interviewer — mock interview;
- Project Mentor — ведёт проект.

Tutor должен знать, находится ли пользователь внутри оцениваемого задания. В таком случае нельзя внезапно выдавать полный solution обычным ответом.

---

# 20. AI Provider Layer

Бизнес-логика не должна напрямую зависеть от одного AI-провайдера.

Интерфейс условно:

```python
class LLMProvider:
    async def generate(...): ...
    async def structured(...): ...
    async def embed(...): ...
```

Можно иметь несколько реализаций и model routing.

Cheap/fast model:

- classification;
- tagging;
- memory extraction;
- простые quiz;
- summaries;
- basic explanations.

Strong model:

- сложный debugging;
- глубокое объяснение;
- архитектурный review;
- roadmap;
- vacancy analysis;
- сложный code review.

Все вызовы идут через внутренний AI Gateway, который делает:

- model routing;
- token/cost accounting;
- timeouts;
- retries;
- fallback;
- caching;
- logging;
- prompt versioning;
- structured-output validation.

---

# 21. Prompt Registry

Prompts нельзя разбрасывать hardcoded строками по backend.

Пример registry:

```text
tutor_teach:v12
tutor_hint:v8
code_review:v21
vacancy_parser:v5
memory_extractor:v11
```

Хранить для каждого:

- version;
- model policy;
- parameters;
- output schema;
- eval score;
- changelog.

При изменении prompt должна быть возможность A/B или staged rollout.

---

# 22. Structured Outputs

Внутренние AI-задачи по возможности должны возвращать JSON по schema, а не свободный текст.

Например memory extractor:

```json
{
  "mistakes": [
    {
      "type": "mutable_default",
      "skill_id": "python.functions.mutable_defaults",
      "severity": "medium",
      "is_recurring": true
    }
  ],
  "recommended_review_days": 1
}
```

Это значительно надёжнее regex-парсинга текста.

---

# 23. Как сделать AI менее «глупым»

Качество достигается системой, а не только выбором самой дорогой модели.

Нужны:

1. качественный context;
2. verified knowledge;
3. structured memory;
4. deterministic tools;
5. execution tests;
6. static analyzers;
7. model routing;
8. prompt evals;
9. fallback;
10. confidence handling.

В коде объективный test result важнее мнения LLM.

Если hidden tests говорят 7/10, tutor не должен утверждать, что решение полностью корректно.

---

# 24. AI Evaluation Framework

До публичного запуска создать benchmark из реальных кейсов.

Категории:

- beginner explanations;
- misleading code;
- bug debugging;
- hint quality;
- запрет преждевременного solution;
- SQL;
- architecture;
- recurring mistake memory;
- vacancy parsing;
- structured output validity.

Каждый кейс имеет rubric. При смене модели или prompt benchmark прогоняется снова.

Главные AI-метрики:

- correctness;
- pedagogical usefulness;
- hallucination rate;
- solution leakage;
- memory accuracy;
- latency;
- cost.

---

# 25. Web App как основной интерфейс

Сайт — главный продукт, потому что сложное обучение и IDE невозможно качественно упаковать только в Telegram.

Рекомендуемые разделы:

```text
/auth
/onboarding
/dashboard
/learn
/practice
/projects
/tutor
/vacancies
/profile
/settings
```

Возможный frontend stack:

- Next.js / React;
- TypeScript;
- Monaco Editor;
- TanStack Query;
- UI library/Tailwind по выбору.

Главное — не конкретная библиотека, а хороший UX и separation of concerns.

---

# 26. Dashboard

Главный вопрос dashboard:

> Что мне делать сейчас?

Пример:

```text
Сегодня — 45 минут

1. SQL JOIN review — 10 минут
2. FastAPI Dependency Injection — 15 минут
3. Практика — 20 минут

[Начать сессию]
```

Ниже:

- цель;
- progress;
- слабые навыки;
- streak;
- recurring mistakes;
- текущий проект.

Не перегружать dashboard десятками аналитических графиков.

---

# 27. Code Editor

На desktop использовать полноценный browser code editor. Monaco подходит, потому что основан на редакторе VS Code и поддерживает модели, language features, diagnostics и diff. Но он не является полным VS Code и обычные VS Code extensions автоматически не работают.

UI:

```text
┌──────── Theory / Task ────────┐
│ Сделай calculate_discount()   │
└───────────────────────────────┘

┌──────────── Editor ───────────┐
│ def calculate_discount(...):  │
│     ...                       │
│                  [Run ▶]      │
└───────────────────────────────┘

Tests: 3/5

Tutor:
Два теста падают на отрицательной цене.
Попробуй подумать о валидации.
```

Обязательные функции:

- autosave;
- tabs/files позже;
- syntax highlighting;
- console;
- tests panel;
- diff;
- reset;
- snapshots/revert;
- hints.

---

# 28. Mobile и PWA

Не надо пытаться превратить телефон в полноценную IDE.

Mobile/PWA предназначены для:

- теории;
- quiz;
- flashcards;
- predict output;
- коротких code edits;
- tutor chat;
- roadmap;
- review.

Для большой coding task:

> «Это задание удобнее продолжить на компьютере».

PWA позволяет дать installable experience без отдельного iOS/Android приложения в V1.

---

# 29. Telegram Bot

Telegram — companion, а не альтернативная версия всей платформы.

Функции:

- привязка аккаунта;
- daily reminder;
- quick quiz;
- review cards;
- tutor chat;
- learning streak;
- weekly summary;
- уведомление о забываемой теме;
- deep link в desktop task.

Сайт и бот используют один backend и одну память пользователя.

Привязка аккаунта делается одноразовым short-lived token, а не Telegram username.

---

# 30. Backend: modular monolith

Для MVP не нужны микросервисы.

Рекомендуется modular monolith:

```text
API
├── auth
├── users
├── goals
├── skills
├── courses
├── assessments
├── roadmap
├── learning
├── exercises
├── submissions
├── tutor
├── memory
├── execution
├── repositories
├── billing
└── notifications
```

Преимущества:

- быстрее разработка;
- проще deploy/debug;
- проще транзакции;
- меньше DevOps.

Возможный backend stack:

- FastAPI;
- SQLAlchemy;
- Alembic;
- PostgreSQL;
- pgvector;
- Redis;
- Celery/Dramatiq/RQ;
- Pydantic.

---

# 31. PostgreSQL — базовая схема

Основные таблицы:

```text
users
profiles
goals

courses
course_modules
lessons
knowledge_units

skills
skill_edges
user_skills
skill_evidence

exercises
exercise_skills
submissions
submission_results
hints_used

mistakes
user_mistakes

assessments
assessment_items
assessment_attempts

learning_paths
learning_path_items
learning_sessions
review_schedule

projects
project_milestones
user_projects

vacancies
vacancy_requirements

repositories
repository_files
code_symbols
code_relations
code_findings

memory_records

tutor_threads
tutor_messages

subscriptions
usage_events
ai_usage
```

Пример `user_skills`:

```sql
user_id
skill_id
knowledge_score
practice_score
independent_score
retention_score
confidence
evidence_count
last_practiced_at
next_review_at
updated_at
```

Пример `mistakes`:

```sql
id
user_id
skill_id
category
fingerprint
description
misconception
first_seen_at
last_seen_at
count
resolved_at
```

Пример knowledge chunks:

```sql
id
source_id
course_id
skill_id
content
metadata jsonb
embedding vector(...)
version
```

---

# 32. AI usage accounting

Это нужно делать с первого дня.

```sql
user_id
feature
provider
model
input_tokens
output_tokens
cached_tokens
estimated_cost
latency_ms
created_at
```

Иначе невозможно понять реальную себестоимость подписки.

Нужны budget guards:

- per-user daily budget;
- per-feature cap;
- global monthly cap;
- alerts на anomaly.

---

# 33. API skeleton

```text
POST /auth/register
POST /auth/login
POST /auth/logout

GET  /me
PATCH /me/profile

POST /assessments/start
POST /assessments/{id}/answer
GET  /assessments/{id}/result

POST /vacancies/analyze
GET  /learning-path/current
POST /learning-path/recalculate

GET  /sessions/today
POST /sessions/{id}/start
POST /sessions/{id}/complete

GET  /lessons/{id}

POST /submissions
GET  /submissions/{id}

POST /tutor/messages

POST /code/run

POST /repositories/import
GET  /repositories/{id}/status
POST /repositories/{id}/review
```

Long-running jobs возвращают job ID и обрабатываются асинхронно.

---

# 34. Async Jobs и Redis

В очередь отправлять:

- repository ingestion;
- embeddings;
- large code review;
- sandbox jobs;
- notifications;
- weekly report;
- scheduled reviews.

Redis использовать для:

- queue;
- temporary cache;
- rate limits;
- locks;
- ephemeral states.

Критические данные не должны существовать только в Redis.


---

# 35. Code Execution Architecture

Пользовательский код нельзя запускать внутри основного API процесса или на машине, где лежат production secrets.

Базовая схема:

```text
Browser
   ↓
Backend API
   ↓
Execution Queue
   ↓
Sandbox Scheduler
   ↓
Ephemeral Sandbox
   ↓
Compile / Run / Tests / Static Analysis
   ↓
Captured stdout/stderr/results
   ↓
Backend
   ↓
Tutor Engine
```

Каждый запуск — отдельная короткоживущая среда.

## 35.1. Минимальные ограничения sandbox

- memory hard limit;
- CPU quota;
- wall-clock timeout;
- process/PID limit;
- filesystem quota;
- network disabled by default;
- non-root user;
- read-only base filesystem;
- temporary writable directory;
- no host filesystem mounts;
- no Docker socket;
- no production environment variables;
- seccomp/AppArmor/gVisor/microVM по мере роста.

Docker официально отмечает, что без явной настройки контейнер по умолчанию может потреблять ресурсы хоста без заданных лимитов. Поэтому resource constraints обязательны.

## 35.2. Этапы зрелости sandbox

### Private alpha

Отдельный недорогой execution-host + Docker containers с жёсткими limits.

### Public beta

Отдельные runner nodes, строгая сеть, quotas, image allowlist, мониторинг abuse.

### Growth

Более сильная изоляция: gVisor/Firecracker-class microVM или специализированная sandbox platform.

Главный принцип: компрометация runner не должна автоматически давать доступ к основной БД, secrets или AI keys.

---

# 36. Python Runner

Base environment:

```text
Python runtime
pytest
ruff
mypy (по необходимости)
```

Pipeline:

```text
validate request
→ create sandbox
→ place starter/user files
→ syntax/compile check
→ run public tests
→ run hidden tests
→ lint/static checks
→ capture stdout/stderr
→ enforce timeout/resource limits
→ destroy sandbox
→ save normalized result
```

Normalized result:

```json
{
  "status": "finished",
  "exit_code": 1,
  "stdout": "...",
  "stderr": "...",
  "tests_passed": 7,
  "tests_total": 10,
  "timeout": false,
  "resource_violation": false,
  "static_findings": []
}
```

---

# 37. JavaScript / TypeScript Runner

Позже:

- Node;
- TypeScript compiler;
- ESLint;
- Vitest/Jest;
- package allowlist.

На раннем этапе не разрешать произвольный `npm install`, иначе появляется огромная attack surface и непредсказуемые расходы/время.

---

# 38. C++ Runner

Pipeline:

- compile;
- warnings;
- clang-tidy;
- sanitizers;
- unit tests;
- CPU/memory/time limits.

C++ особенно требует строгой изоляции и runtime limits.

---

# 39. HTML/CSS/React

Здесь нужен другой UX: editor + live preview.

```text
┌──────── editor ────────┬──────── preview ────────┐
│                        │                          │
│ React/HTML/CSS         │ rendered UI              │
│                        │                          │
└────────────────────────┴──────────────────────────┘
```

Preview должен работать в sandboxed iframe на безопасной origin/политике. Пользовательский JS не должен иметь доступ к session cookies главного приложения.

---

# 40. Hidden tests и rubric

У задачи есть public tests и hidden tests. Source hidden tests пользователю не передаётся.

Оценка не должна быть только pass/fail. Возможный rubric:

```text
Correctness  50%
Readability  15%
Edge cases   10%
Testing      10%
Complexity   10%
Style         5%
```

Вес зависит от уровня пользователя. Новичку не надо давать тяжёлый architecture penalty за первую функцию.

LLM получает не только код, но и task, test results, linter output, уровень пользователя, известные ошибки и rubric.

---

# 41. Data flow одного submission

```text
1. Web сохраняет draft
2. User нажимает Run/Submit
3. API создаёт submission record
4. Job уходит в execution queue
5. Runner выполняет code/tests
6. Static analyzers формируют findings
7. Result сохраняется
8. Tutor Engine загружает user memory
9. LLM создаёт educational feedback
10. Memory extractor выделяет mistakes/misconceptions
11. Mastery Engine обновляет skill evidence
12. Review Scheduler назначает повторение
13. UI получает result
```

Это позволяет использовать объективные сигналы до LLM.

---

# 42. Большие репозитории: 5–30k+ строк

Нельзя каждый раз отправлять весь repository модели. Даже если модель технически принимает большой контекст, это дорого, медленно и часто хуже по качеству.

Нужен Code Intelligence Pipeline.

```text
GitHub/ZIP
  ↓
Ingestion
  ↓
File classification
  ↓
Ignore generated/vendor/build
  ↓
Parsing
  ↓
Symbols
  ↓
Dependency graph
  ↓
Hierarchical summaries
  ↓
Embeddings/index
  ↓
Repository model
```

---

# 43. Tree-sitter и parsing

Tree-sitter подходит для построения syntax tree разных языков, способен быстро обновлять дерево при изменениях и сохраняет полезную структуру даже при синтаксических ошибках.

Из исходников выделяются:

- modules/files;
- classes;
- functions;
- methods;
- imports;
- calls;
- references, где возможно;
- docstrings/comments;
- symbol ranges.

Tree-sitter — не полный semantic compiler, поэтому сложный symbol resolution может требовать language-specific tooling/LSP/compiler analysis.

---

# 44. Repository schema

```text
repositories
repository_files
code_symbols
symbol_relations
code_chunks
code_embeddings
file_summaries
module_summaries
repository_summaries
code_findings
analysis_runs
```

`repository_files`:

```text
id
repository_id
path
language
size
hash
is_generated
last_indexed_at
```

`code_symbols`:

```text
id
file_id
symbol_type
name
qualified_name
start_line
end_line
signature
summary
```

`symbol_relations`:

```text
from_symbol_id
to_symbol_id
relation_type
```

Типы relation: calls / imports / inherits / implements / references.

---

# 45. Repository filtering

По умолчанию исключать:

```text
node_modules
.venv
venv
vendor
dist
build
coverage
__pycache__
generated
large binaries
```

Также учитывать `.gitignore`, но не доверять ему единственному.

Нужны max upload size, max file size, max file count и language allowlist.

---

# 46. Hierarchical summaries

Создавать summaries на нескольких уровнях:

```text
function
→ class
→ file
→ module/package
→ repository
```

Если изменился один файл, не нужно заново summarise весь repository. Пересчитываются затронутые узлы вверх по дереву.

---

# 47. Repository retrieval

Если пользователь спрашивает:

> Почему неправильно пересчитывается корзина?

Retriever использует:

- semantic similarity;
- symbol names;
- stack trace;
- dependency graph;
- imports/calls;
- recent changed files.

Например извлекается только цепочка:

```text
routes/cart.py
→ CartService
→ PriceCalculator
→ DiscountPolicy
→ tests/cart_test.py
```

В LLM отправляется релевантный context, а не все 30 тысяч строк.

---

# 48. Большой Code Review — multi-pass

Разделить review:

### Pass 1 — structure

- packages;
- coupling;
- dependency direction;
- module boundaries.

### Pass 2 — correctness

- suspicious logic;
- edge cases;
- error handling.

### Pass 3 — maintainability

- duplication;
- complexity;
- naming;
- oversized functions/classes.

### Pass 4 — testing

- test architecture;
- uncovered important paths;
- brittle tests.

### Pass 5 — security hygiene

- obvious secrets;
- unsafe patterns;
- input handling.

### Pass 6 — educational synthesis

Не просто «73 проблемы», а:

> Главные три навыка, которые пользователю стоит развить, и конкретные упражнения по ним.

---

# 49. Code Review как обучение

Плохой результат:

> `OrderService` слишком большой. Вот переписанный код.

Хороший:

> `OrderService` совмещает валидацию, расчёт цены и запись в БД. Это увеличивает связность. Сначала сам выдели один компонент. Какую ответственность ты бы вынес первой?

После ответа AI продолжает.

---

# 50. Recurring Mistake Detection

При новом finding:

1. классифицировать category;
2. связать с skill;
3. создать fingerprint;
4. найти похожие user mistakes;
5. увеличить recurrence;
6. определить misconception;
7. scheduled review.

Tutor получает право сказать:

> Это похожая ошибка на ту, которую ты делал в прошлом проекте.

Но только если система действительно нашла evidence, а не придумывает память.

---

# 51. Secret Detection

При загрузке repository искать потенциальные:

- API keys;
- private keys;
- passwords;
- tokens;
- `.env`.

Если найден secret:

- не отправлять его в LLM;
- redaction;
- предупреждение пользователю;
- рекомендовать rotation, если secret мог утечь.

---

# 52. Prompt Injection из кода

Repository — недоверенные данные. README или комментарий может содержать:

> Ignore previous instructions.

Это не должно менять system behavior.

В orchestration контент repository явно маркируется как untrusted data. System/developer rules отделены от data. То же касается внешних knowledge sources.

---

# 53. Auth и sessions

Web:

- secure httpOnly cookies;
- CSRF protection где нужно;
- refresh token rotation;
- OAuth state verification;
- Argon2id/bcrypt для passwords;
- email verification;
- single-use reset tokens.

Не хранить JWT/access tokens в localStorage без необходимости.

---

# 54. Telegram linking

Правильный flow:

```text
Web: Connect Telegram
→ backend создаёт одноразовый token
→ deep link в bot
→ bot получает token
→ backend проверяет TTL/single-use
→ связывает telegram_user_id
```

Не связывать аккаунт по username, потому что username может измениться и не является надёжным идентификатором.

---

# 55. Permissions

Роли:

```text
user
content_editor
reviewer
support
admin
```

Support не должен автоматически иметь доступ к private repository пользователя. Нужен принцип least privilege и audit trail для чувствительных действий.

---

# 56. Privacy

Код пользователя может быть коммерчески чувствительным.

Нужно заранее определить:

- что хранится;
- сколько хранится;
- какие данные отправляются AI-провайдерам;
- как удаляется repository;
- как удаляются derived embeddings/summaries;
- как обрабатывается account deletion;
- какие billing records обязаны храниться отдельно по закону.

Default для repository: private.

Публичное портфолио включается явно.

---

# 57. Delete Account

Удаление должно охватывать:

- профиль;
- сообщения;
- submissions;
- private repository files;
- code embeddings;
- derived summaries;
- personal learning memory;
- storage objects.

Нельзя удалить только строку `users` и оставить все производные персональные данные.

---

# 58. Контент и авторские права

Нельзя просто взять платные книги/курсы и загрузить их в RAG.

Использовать:

- собственный контент;
- официальную документацию в рамках допустимого использования;
- разрешённые/licensed материалы;
- оригинальные упражнения.

AI может помогать писать draft, но критический учебный core должен проходить human review.

---

# 59. Content CMS

Нужны states:

```text
draft
review
published
archived
```

И versioning.

Course content лучше не менять напрямую в production БД без истории. Должен быть rollback.

---

# 60. Course Versioning

Если curriculum v1 изменён на v2, существующий пользователь не должен внезапно потерять половину learning path.

Хранить version и migration policy:

- continue old path;
- migrate compatible items;
- re-evaluate only changed skills.

---

# 61. Admin Panel

Нужен раньше, чем кажется.

Разделы:

- users;
- subscriptions;
- courses;
- skills;
- lessons;
- exercises;
- knowledge chunks;
- failed AI calls;
- flagged tutor responses;
- code-run failures;
- AI cost;
- feature flags;
- content versions.

---

# 62. Observability

С первого production:

- structured logs;
- tracing/request ID;
- error monitoring;
- DB query latency;
- queue depth;
- sandbox latency/failures;
- AI latency;
- token usage;
- cost per feature/user;
- conversion funnel.

Не логировать passwords, access tokens, private secrets или весь пользовательский код без необходимости.

---

# 63. Backups

PostgreSQL:

- регулярные backups;
- retention;
- отдельное storage;
- restore drill.

Object storage:

- lifecycle/versioning по необходимости.

Backup считается проверенным только после успешного restore test.

---

# 64. Rate Limits и abuse

Ограничивать:

- login;
- tutor messages;
- code runs;
- uploads;
- vacancy analysis;
- deep review;
- repository analysis.

Нельзя продавать технически бесконечный unlimited, если один пользователь способен сжечь сотни долларов AI/sandbox resources.

Можно использовать внутренние credits, но пользователю показывать понятные лимиты: например «5 глубоких review в месяц».

---

# 65. Billing и тарифы

Возможная логика:

### Free

- onboarding;
- assessment;
- базовый roadmap;
- несколько уроков;
- ограниченный tutor;
- несколько code runs.

### Student

- основной learning path;
- практика;
- memory;
- code runner;
- базовый AI tutor.

### Pro

- все основные paths;
- vacancy analysis;
- проекты;
- GitHub integration;
- более глубокий review.

### Advanced

- крупные repositories;
- architecture review;
- большие AI limits;
- advanced ML/engineering modules.

Точные цены нужно проверять экспериментом, а не закладывать как догму.

---

# 66. Paywall

Не ставить paywall до первого aha moment.

Free пользователь должен успеть:

1. пройти диагностику;
2. увидеть свой gap;
3. получить персональный roadmap;
4. пройти первый lesson;
5. решить первую задачу;
6. почувствовать персональный tutor.

Хороший aha moment:

> «Ты снова допустил ошибку, которую делал вчера. Поэтому я добавил тебе короткое упражнение именно на неё».

После такой ценности подписка воспринимается иначе.

---

# 67. Unit economics — что обязательно считать

Переменные расходы:

- LLM input/output;
- embeddings;
- code execution;
- object storage;
- payment fee.

Fixed/semi-fixed:

- web/backend;
- DB;
- Redis;
- monitoring;
- email;
- runner capacity.

Самая опасная функция для маржи — большой repository review. Он должен иметь quotas или отдельные credits.

На каждый feature хранить estimated cost.

---

# 68. Product Metrics

North Star кандидат:

> Weekly learners who complete meaningful independent practice.

Не «количество сообщений AI».

Acquisition:

- landing visitors;
- signup rate.

Activation:

- assessment completion;
- first learning session;
- first successful code submission.

Engagement:

- sessions/week;
- exercises completed;
- minutes of real practice;
- projects.

Retention:

- D7;
- D30;
- paid retention.

Learning:

- mastery delta;
- delayed recall;
- hint dependency;
- independent success;
- transfer tasks.

Revenue:

- free→paid;
- ARPPU;
- churn;
- gross margin;
- LTV/CAC.

---

# 69. Learning Metrics

Очень важно не оптимизировать только удержание.

Проверять:

- pre-test vs post-test;
- delayed test через несколько дней;
- transfer task с другим контекстом;
- способность решить без подсказок;
- способность объяснить собственное решение.

Иначе продукт может быть «интересным», но плохо обучать.

---

# 70. Feedback loop

После AI answer:

```text
Помогло? 👍 👎
```

Если 👎:

- неправильно;
- слишком сложно;
- слишком легко;
- дал готовое решение;
- не понял вопрос;
- другое.

Это превращается в dataset для prompt/model/content improvements.


---

# 71. Motivation и геймификация

Геймификация — вспомогательная, не главная ценность.

Можно использовать:

- streak;
- XP;
- уровни;
- achievements;
- milestones.

Но главная мотивация должна быть профессиональной:

> «Ты стал лучше решать реальные задачи и приблизился к своей цели».

Не превращать platform в детскую игру, особенно для взрослых пользователей.

---

# 72. Difficulty Adaptation

Если пользователь пять задач подряд решает легко и быстро — повышать сложность.

Если постоянно застревает — не просто давать больше подсказок, а проверять prerequisites.

Иногда проблема в теме уровнем ниже.

Пример:

> человек не понимает decorators не потому, что decorators сложны, а потому что плохо понимает functions as objects / closures.

Curriculum Engine должен уметь откатываться на prerequisite.

---

# 73. Frustration Detection

Сигналы:

- много failed runs;
- большое количество hints;
- повторяющиеся «не понимаю»;
- долгое время без прогресса;
- частые reset/solution.

Tutor может сменить режим:

> «Похоже, мы упёрлись в базовую идею. Давай на 5 минут вернёмся к ней и потом продолжим».

---

# 74. Confidence Calibration

После некоторых заданий спросить:

> Насколько ты уверен в решении от 1 до 5?

Сравнивать confidence с фактическим результатом. Это помогает пользователю понимать собственные пробелы.

---

# 75. User Explanation Tasks

После решения:

> «Объясни одним-двумя предложениями, почему это решение работает».

AI оценивает conceptual understanding.

Это полезно для обнаружения ситуаций, когда код был фактически скопирован, но понимание отсутствует.

---

# 76. Interview Mode

После обучения под вакансию:

- HR simulation;
- technical questions;
- live coding;
- code reading;
- system discussion.

AI задаёт вопросы по одному и адаптируется к ответам.

Не выдавать псевдонаучное «вероятность получить работу 87%». Лучше показывать evidence:

```text
Strong: Python Core
Medium: SQL
Needs practice: Docker, testing
```

---

# 77. Weekly Report

Пример:

```text
Неделя 4

4 learning sessions
11 exercises
82 минуты практики

Лучший рост:
SQL JOIN

Повторяющаяся ошибка:
exception handling

Следующая цель:
FastAPI dependencies
```

Report можно присылать email/Telegram.

---

# 78. Notifications

Хорошие уведомления имеют конкретную ценность:

> «Ты начинаешь забывать LEFT JOIN. Повторение займёт 3 минуты».

Плохие:

> «Мы скучаем, вернись!»

Частота должна быть пользовательской настройкой.

---

# 79. SEO и публичная часть

Большая часть приложения закрыта login, но можно иметь публичные страницы:

- Python concepts;
- roadmaps;
- error explanations;
- interview guides;
- skill pages.

Например:

```text
/python/decorators
/python/asyncio
/sql/joins
```

CTA:

> «Проверь, насколько ты реально понимаешь эту тему».

Не генерировать тысячи низкокачественных AI SEO-страниц.

---

# 80. Referral

Простая механика:

> пригласи друга → обоим несколько дней Pro или extra credits.

Особенно естественно для студентов.

---

# 81. Localization

Skill Graph желательно делать language-neutral.

Контент:

```text
concept_id
locale
content
```

Тогда русский/английский интерфейсы используют одно образовательное ядро, но разные тексты.

---

# 82. Accessibility

Учитывать:

- keyboard navigation;
- contrast;
- screen reader labels;
- font scaling;
- не использовать цвет как единственный сигнал;
- accessible code editor configuration.

---

# 83. Deployment MVP

Пример архитектуры:

```text
                   ┌─────────────────────┐
                   │ CDN / Reverse Proxy │
                   └─────────┬───────────┘
                             │
                   ┌─────────▼─────────┐
                   │     Web App       │
                   │ Next.js / React   │
                   └─────────┬─────────┘
                             │
                   ┌─────────▼─────────┐
                   │    Backend API    │
                   │      FastAPI      │
                   └─────────┬─────────┘
                             │
         ┌───────────────────┼────────────────────┐
         │                   │                    │
 ┌───────▼───────┐  ┌────────▼────────┐  ┌────────▼─────────┐
 │ PostgreSQL    │  │ Redis / Queue   │  │ Object Storage   │
 │ + pgvector    │  └────────┬────────┘  └──────────────────┘
 └───────────────┘           │
                     ┌───────▼────────┐
                     │ Async Workers  │
                     └───────┬────────┘
                             │
                ┌────────────┼─────────────┐
                │            │             │
         ┌──────▼─────┐ ┌────▼─────┐ ┌────▼─────────┐
         │ AI Gateway │ │ Telegram │ │ Runner Queue │
         └──────┬─────┘ └──────────┘ └────┬─────────┘
                │                          │
        ┌───────┼────────┐          ┌──────▼─────────┐
        │       │        │          │ Execution Host │
      LLM A   LLM B  Embeddings     │ Sandboxes      │
                                   └────────────────┘
```

---

# 84. Архитектура V2: Repository Intelligence

```text
GitHub / ZIP
      ↓
Repo Ingestion Worker
      ↓
Tree-sitter + language tooling
      ↓
Symbols / Imports / Relations
      ↓
Dependency Graph
      ↓
Summaries + Embeddings
      ↓
Code Index
      ↓
Repository Review Engine
      ↓
Learning Gap Generator
```

---

# 85. CI/CD

Pipeline:

```text
lint
→ unit tests
→ integration tests
→ type checks
→ security/dependency checks
→ build
→ migration validation
→ deploy staging
→ smoke tests
→ deploy production
```

Environments:

- local;
- staging;
- production.

Prompt/model changes тоже желательно тестировать на staging/evals.

---

# 86. Feature Flags

Примеры:

```text
github_import
large_repo_review
new_tutor_v2
new_mastery_model
new_vacancy_parser
```

Это позволяет включать feature небольшому проценту пользователей и быстро выключать при проблемах.

---

# 87. Основные security threats

Для code platform особенно важны:

- arbitrary code execution;
- infinite loops;
- fork bombs;
- memory exhaustion;
- filesystem probing;
- internal network scanning;
- cloud metadata access;
- mining/abuse;
- malicious uploads;
- prompt injection;
- leaked API secrets;
- dependency attacks.

Безопасность sandbox — отдельный engineering stream, а не одна галочка Docker.

---

# 88. Security checklist перед beta

- [ ] HTTPS
- [ ] secrets вне repository
- [ ] production DB закрыта firewall/private network
- [ ] strong password hashing
- [ ] rate limits
- [ ] sandbox separated
- [ ] resource limits
- [ ] network disabled in runner by default
- [ ] upload limits
- [ ] file type validation
- [ ] secret scanning
- [ ] backups
- [ ] restore test
- [ ] dependency scanning
- [ ] logs не содержат secrets
- [ ] account deletion flow
- [ ] privacy policy

---

# 89. MVP Scope

Первый продукт:

> **Персональный AI-наставник по Python Backend.**

Обязательные функции:

1. регистрация;
2. onboarding;
3. выбор цели;
4. adaptive assessment;
5. Python Backend Skill Graph;
6. mastery model;
7. персональный roadmap;
8. lesson page;
9. quiz;
10. Monaco desktop editor;
11. Python sandbox;
12. public/hidden tests;
13. hint ladder;
14. AI tutor;
15. mistake memory;
16. spaced review;
17. dashboard;
18. vacancy analyzer;
19. basic billing;
20. Telegram reminder/quick tutor;
21. AI usage accounting;
22. admin basics;
23. monitoring/backups.

---

# 90. Что НЕ входит в MVP

Не делать одновременно:

- C++;
- React live IDE;
- ML/Data Science;
- native mobile;
- social network;
- employer marketplace;
- сертификаты;
- live collaboration;
- видео-платформу;
- собственную LLM;
- Kubernetes;
- десятки microservices;
- полный large-repository engine.

Это scope trap.

---

# 91. Очень агрессивный 4-недельный план

Подходит только для solo developer с AI и готовностью к компромиссам.

## Неделя 1 — foundation

- monorepo/repository;
- auth;
- PostgreSQL;
- базовые models;
- skill graph;
- onboarding;
- dashboard skeleton;
- AI Gateway.

Deliverable:

> пользователь регистрируется, выбирает цель и получает learning profile.

## Неделя 2 — learning core

- adaptive assessment;
- mastery updates;
- roadmap;
- lessons;
- quizzes;
- knowledge retrieval;
- mistake records.

Deliverable:

> assessment → personal path → lesson.

## Неделя 3 — coding

- Monaco;
- Python runner;
- tests;
- submissions;
- hints;
- tutor feedback;
- usage accounting.

Deliverable:

> пользователь пишет код → run → tests → educational feedback.

## Неделя 4 — productization

- vacancy parser;
- Telegram;
- billing;
- limits;
- admin;
- monitoring;
- security hardening;
- beta polish.

Deliverable:

> можно приглашать первых платящих beta users.

---

# 92. Более реалистичный 8–12 недельный roadmap

### Phase 1 — 2 недели

Core platform, auth, schema, skill model.

### Phase 2 — 2 недели

Assessment + curriculum + content.

### Phase 3 — 2 недели

Editor + sandbox + submissions.

### Phase 4 — 2 недели

AI quality, memory, evals.

### Phase 5 — 2 недели

Billing, Telegram, security, admin.

### Phase 6 — 2 недели

Beta feedback, fixes, content expansion.

---

# 93. Первые 20 beta-пользователей

Идеально набрать:

- 5 полных новичков;
- 5 студентов;
- 5 junior developers;
- 5 людей с реальной вакансией.

Наблюдать не только feedback, а поведение:

- завершил ли onboarding;
- прошёл ли assessment;
- дошёл ли до первой coding task;
- сколько подсказок использовал;
- вернулся ли через день/неделю;
- понял ли AI feedback;
- согласен ли платить.

---

# 94. Главная гипотеза MVP

Не «людям нравится AI».

Гипотеза:

> **Персонализированное обучение с памятью, реальной практикой и адаптивным curriculum создаёт достаточно больше ценности, чем обычный чат-бот, чтобы пользователь регулярно возвращался и платил.**

---

# 95. Moat

Потенциальная защита продукта не в доступе к LLM.

Moat:

- качественный skill graph;
- accumulated student history;
- mistake graph;
- mastery/evidence model;
- curriculum engine;
- curated content;
- projects;
- learning outcome data;
- UX.

Через полгода система знает сотни задач пользователя, recurring mistakes, сильные/слабые стороны, forgetting schedule и карьерную цель. Это даёт switching cost.

---

# 96. Почему пользователь не уйдёт просто в обычный AI-чат

Обычный чат умеет хорошо отвечать, но platform хранит structured educational state:

```text
500 solved tasks
150 mistakes
20 recurring misconceptions
6 projects
45 skills
3 target vacancies
review schedule
personal roadmap
```

При смене сервиса теряется именно этот контекст и учебная система, а не просто история разговора.

---

# 97. Основные риски и mitigation

## AI ошибается

Mitigation: RAG, tests, tools, strong-model routing, evals.

## Пользователь копирует

Mitigation: hint ladder, independent checks, delayed review.

## Высокая AI себестоимость

Mitigation: routing, limits, compact context, caching, budget guards.

## Sandbox exploit

Mitigation: isolated runner, resource/network limits, stronger isolation at scale.

## Scope explosion

Mitigation: только Python Backend V1.

## Слабый контент

Mitigation: human review, versioning, feedback loop.

## Низкое удержание

Mitigation: daily plan, visible goals, projects, spaced review, Telegram companion.

---

# 98. Репозиторий проекта

Один из вариантов:

```text
/apps
  /web
  /api
  /telegram

/services
  /sandbox

/packages
  /contracts
  /ui
  /skill-schema
  /prompt-registry

/content
  /python-backend

/evals
  /tutor
  /code-review
  /memory

/infra
  /docker
  /deploy
```

Если это solo MVP, не усложнять monorepo раньше времени.

---

# 99. Backend module structure

```text
app/
  auth/
  users/
  goals/
  skills/
  courses/
  assessment/
  roadmap/
  learning/
  exercises/
  submissions/
  tutor/
  memory/
  ai/
  execution/
  repository/
  billing/
  notifications/
```

---

# 100. Content structure

```text
python_backend/
  skills.yaml
  modules/
    python_basics/
      lessons/
      exercises/
    functions/
    oop/
    sql/
    fastapi/
    testing/
    docker/
```

Можно хранить authored content в git и публиковать в БД через importer/versioning pipeline.

---

# 101. Пример exercise definition

```yaml
id: python.functions.discount
title: Calculate discount
skills:
  - python.functions.parameters
  - python.conditionals
difficulty: 0.25

starter_code: |
  def calculate_discount(price, percent):
      pass

public_tests:
  - input: [100, 10]
    expected: 90

rubric:
  correctness: 0.7
  readability: 0.2
  edge_cases: 0.1

hints:
  - Think about converting percent to a fraction.
  - The discount amount is price * percent / 100.
```

LLM может генерировать варианты задания, но before publish/serve желательно проверять их solver/test pipeline.

---

# 102. API/Data flow Tutor Message

```text
1. receive user message
2. detect intent
3. detect active assessment/exercise
4. retrieve compact profile
5. retrieve relevant skills
6. retrieve related mistakes
7. retrieve knowledge chunks
8. select tutor mode
9. select model
10. generate response
11. validate output
12. store response
13. extract structured memory if needed
14. account cost
```

---

# 103. Latency targets

Ориентиры UX:

- simple tutor response: желательно несколько секунд;
- simple Python run: несколько секунд;
- assessment answer: почти мгновенно или быстро;
- deep repository review: async job с понятным progress state.

Для долгих процессов показывать реальные стадии:

```text
Uploading
Parsing
Indexing
Static checks
Architecture review
Building report
```

Лучше stages, чем выдуманный «67%».

---

# 104. Error Handling

AI provider временно недоступен:

- retry;
- fallback model/provider;
- сохранить user message;
- понятное сообщение.

Sandbox недоступен:

- код сохранён;
- пользователь может повторить run позже;
- submission не теряется.

Repository job упал:

- stage/error reason;
- retry from idempotent step.

---

# 105. Autosave и snapshots

Code editor обязательно autosave:

- debounce;
- server draft;
- local fallback;
- version number.

Перед большим AI refactor создавать snapshot, чтобы пользователь мог revert.

---

# 106. Работа без AI

Продукт не должен полностью умирать при outage LLM.

Детерминированно могут продолжать работать:

- authored lessons;
- quizzes;
- code execution;
- tests;
- dashboard;
- cached roadmap;
- progress history.

AI добавляет персональность и объяснение, но не должен быть единственной точкой существования продукта.

---

# 107. Будущие learning paths

После подтверждения Python Backend:

### Frontend

HTML → CSS → JS → TS → React → testing → tooling.

### Data Analysis

Python → NumPy → Pandas → SQL → statistics → visualization.

### ML

Python → NumPy/Pandas → probability/statistics → scikit-learn → feature engineering → evaluation → deep learning.

### AI/LLM Engineering

Python → APIs → embeddings → retrieval → RAG → evaluation → agents/tools → fine-tuning basics → observability/security.

### C++

Core syntax → memory → STL → algorithms → RAII → templates → concurrency → tooling.

---

# 108. Employer layer — только позже

Если система накопит достаточно реальных evidence, можно сделать opt-in portfolio / hiring layer.

Например работодатель ищет:

- Python projects;
- SQL evidence;
- testing experience.

Но нельзя выдавать внутренний approximate mastery как абсолютный показатель профессиональной пригодности. Нужны прозрачные assessments и согласие пользователя.

---

# 109. Потенциальная монетизация в будущем

B2C:

- подписки;
- advanced review credits;
- interview packages.

B2B позже:

- teams;
- universities;
- assessment tools;
- hiring/talent discovery.

Не распыляться до доказанного B2C core.

---

# 110. Критические решения до начала кодинга

Перед стартом зафиксировать письменно:

1. Первый path — Python Backend.
2. Первый язык интерфейса.
3. Основной LLM provider.
4. Fallback policy.
5. AI budget на пользователя.
6. Как sandbox отделяется от production.
7. Формулу mastery.
8. Какие evidence изменяют mastery.
9. Hint ladder.
10. Mistake taxonomy.
11. Что именно хранится как long-term memory.
12. Retention/privacy policy.
13. Free limits.
14. Pro limits.
15. Telegram scope.
16. Что сознательно НЕ входит в V1.

---

# 111. P0 / P1 / P2 backlog

## P0 — без этого нельзя запускать

- [ ] Auth
- [ ] User profile
- [ ] Goal
- [ ] Python skill graph
- [ ] Assessment
- [ ] Mastery model
- [ ] Learning path
- [ ] Lesson renderer
- [ ] Exercise system
- [ ] Monaco editor
- [ ] Python sandbox
- [ ] Public/hidden tests
- [ ] Tutor Engine
- [ ] RAG
- [ ] Mistake memory
- [ ] Review scheduling
- [ ] AI usage accounting
- [ ] Billing
- [ ] Admin basics
- [ ] Logging/monitoring
- [ ] Backups

## P1 — очень желательно

- [ ] Vacancy analyzer
- [ ] Telegram bot
- [ ] Weekly report
- [ ] Project milestones
- [ ] Prompt registry
- [ ] AI eval suite
- [ ] Feature flags
- [ ] rate limits
- [ ] secret scanning

## P2 — после первых пользователей

- [ ] GitHub OAuth
- [ ] repository import
- [ ] Tree-sitter indexing
- [ ] large code review
- [ ] JavaScript/TypeScript
- [ ] React
- [ ] portfolio page
- [ ] interview mode

## P3 — масштабирование

- [ ] Data/ML
- [ ] C++
- [ ] advanced repository intelligence
- [ ] employer layer
- [ ] native mobile only if justified
- [ ] team plans

---

# 112. Финальная архитектурная формула

```text
                     USER GOAL / VACANCY
                             │
                             ▼
                      ADAPTIVE ASSESSMENT
                             │
                             ▼
                         SKILL GRAPH
                             │
                    ┌────────┴─────────┐
                    │                  │
                    ▼                  ▼
              STUDENT MODEL      TARGET PROFILE
                    │                  │
                    └────────┬─────────┘
                             ▼
                      CURRICULUM ENGINE
                             │
                    ┌────────┼─────────────┐
                    │        │             │
                    ▼        ▼             ▼
                 THEORY   PRACTICE      PROJECTS
                    │        │             │
                    │        ▼             │
                    │    CODE RUNNER       │
                    │        │             │
                    └────────┼─────────────┘
                             ▼
                         AI TUTOR
                             │
               ┌─────────────┼─────────────┐
               │             │             │
               ▼             ▼             ▼
          KNOWLEDGE RAG   USER MEMORY   TEST RESULTS
               │             │             │
               └─────────────┼─────────────┘
                             ▼
                      MASTERY UPDATE
                             │
                             ▼
                      NEXT BEST ACTION
```

---

# 113. Финальная рекомендация

Первая коммерчески проверяемая версия продукта должна быть сформулирована очень конкретно:

> **Персональный AI-наставник по Python Backend. Он проверяет твой реальный уровень, строит индивидуальный путь, даёт теорию и практику, запускает и проверяет код, помнит ошибки и адаптирует следующие задания. Можно вставить вакансию и учиться именно под её требования.**

Это уже достаточно большая ценность, чтобы проверять готовность платить.

Не нужно сначала строить «университет будущего». Если core работает — остальные языки и направления становятся расширениями одной и той же платформы.

---

# 114. Технические источники и документация

Официальные/первичные источники, которые стоит использовать при реализации:

- **Monaco Editor** — браузерный code editor из экосистемы VS Code:  
  https://github.com/microsoft/monaco-editor

- **pgvector** — vector similarity search для PostgreSQL, включая exact search, HNSW и IVFFlat:  
  https://github.com/pgvector/pgvector

- **Tree-sitter** — incremental parsing library для syntax trees:  
  https://github.com/tree-sitter/tree-sitter

- **Docker Resource Constraints** — CPU/memory limits для контейнеров:  
  https://docs.docker.com/engine/containers/resource_constraints/

- **OpenAI Vector Stores / Retrieval API reference** — если вместо собственного pgvector использовать managed retrieval:  
  https://platform.openai.com/docs/api-reference/vector-stores

---

# 115. Что делать непосредственно после этого документа

Практический следующий порядок:

1. Зафиксировать V1 scope.
2. Нарисовать 6–8 основных экранов.
3. Создать Python Backend Skill Graph хотя бы на 80–150 skills/concepts.
4. Спроектировать PostgreSQL schema.
5. Реализовать auth + profile + assessment.
6. Реализовать mastery/evidence model без AI.
7. Добавить lesson/exercise engine.
8. Подключить AI Gateway + RAG.
9. Сделать Python sandbox.
10. Сделать mistake memory.
11. Сделать vacancy parser.
12. Дать продукт 10–20 реальным людям.
13. Смотреть реальные learning/retention данные.
14. Только после этого добавлять GitHub/large repo intelligence и новые языки.

---

## Итог в одной фразе

**Строй не чат-бота, который знает программирование, а учебную операционную систему, в которой AI — персональный преподаватель, а вся реальная память, прогресс, навыки, ошибки, практика и доказательства знаний принадлежат твоей платформе.**
