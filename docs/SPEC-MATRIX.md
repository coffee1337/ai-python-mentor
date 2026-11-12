# Матрица трассировки: спека → код → тест

Проект **AI Python Mentor**. Документ покрывает три источника требований: `ai_programming_tutor_full_spec.md` (разделы 1–115), `README.md` (обещания в Key Features) и `UNIMPLEMENTED_STAGES.md` (разделы «Требует настройки» и «Осознанные границы»). Дата сверки: 10 ноября 2026.

Каждая строка — одно дискретное требование или тезис. Статус `done` ставится только там, где поведение найдено в коде и покрыто тестом; строка без теста не может быть `done`. Статус `out-of-scope` ставится только при наличии зафиксированного решения: ADR в `docs/decisions.md`, раздел 90 спецификации или `UNIMPLEMENTED_STAGES.md`.

## Сводка

| Показатель | Значение |
|---|---|
| Всего строк | 250 |
| done | 79 |
| partial | 125 |
| missing | 25 |
| out-of-scope | 21 |
| строк без статуса | 0 |

## Легенда

| Статус | Значение |
|---|---|
| `done` | Поведение реализовано и покрыто тестом; файл открыт и проверен. |
| `partial` | Реализовано частично либо реализовано без теста. Причина — в колонке «Комментарий». |
| `missing` | Требования нет в коде. Если вывод из scope не подтверждён ADR, строка остаётся `missing`, а не `out-of-scope`. |
| `out-of-scope` | Есть письменное решение: ADR в `docs/decisions.md`, §90 спецификации или `UNIMPLEMENTED_STAGES.md`. |

Ссылки на тесты даны как `tests/<file>.py::<test_name>` и относятся к `apps/api/tests/`, кроме путей `tests/runner/tests/...` (`apps/runner/tests/`). Ссылки на код — путь от корня репозитория, при необходимости с номером строки. `нет` в колонке «Тест» означает, что теста нет.

## Как проверялось

Ссылки проверялись чтением файлов и `rg`; имена тестов сверялись с AST-разбором тестовых модулей, поэтому все строки ссылаются на существующие файлы и существующие функции тестов. Тесты не запускались: по условию задачи прогон занимает 13+ минут.

```bash
rg -n '^#' ai_programming_tutor_full_spec.md
rg -n '@(router|app)\.(get|post|patch|put|delete)\(' apps/api/app
rg -n '^class .*\(Base\)' apps/api/app/db/*.py
rg -n '^def test_|^    def test_' apps/api/tests apps/runner/tests
rg -n 'def ' apps/api/app/mentor.py apps/api/app/learning.py apps/api/app/curriculum.py
rg -n 'localStorage|draft|debounce|snapshot|revert|diff' apps/web/app/learning
rg -il 'tree-sitter|treesitter|repository_files|code_symbols' apps/api apps/runner
rg -n 'prometheus|opentelemetry|sentry|trace_id' apps/api
rg -n 'redis|FEATURE_FLAG|feature_flag' apps/api apps/runner docker-compose.yml
rg -n 'aria-|role=|tabIndex' apps/web/app --glob '*.tsx'
ls apps/api/migrations/versions apps/web/app apps/runner/runner_worker
```

## §1. Суть продукта

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 1.1 | Адаптивная система: mastery, ошибки, подсказки, цель и вакансия в одной модели | `partial` | `apps/api/app/skill_evidence.py:38; apps/api/app/learning_plan.py:64` | `tests/test_skill_graph.py::test_mastery_fallback_is_consistent_across_path_plan_and_curriculum` | mastery, план и ошибки есть; поведенческой памяти и калибровки нет |
| 1.2 | MVP ограничен Python → Python Backend | `done` | `apps/api/app/skill_graph.py:6; apps/api/app/backend_content.py:1` | `tests/test_backend_track_phase_one.py::test_phase_one_covers_exactly_the_nine_published_backend_skills` | 42 навыка python.core + 48 backend, 90 уроков |
| 1.3 | Формула Skill Graph + Student Model + Memory + Curriculum + KB + Practice + Execution + Tutor + Vacancy | `partial` | `apps/api/app/main.py:51` | `tests/test_practice.py::test_runner_unavailable_configuration_stays_fail_closed` | все контуры смонтированы, но исполнение кода по умолчанию выключено (fail-closed) |

## §2. Какую проблему решает продукт

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 2.1 | Динамический curriculum вместо одинакового курса | `done` | `apps/api/app/curriculum.py:92` | `tests/test_learning_plan.py::test_plan_recommendation_follows_progress_and_reassessment_updates_version` | порядок зависит от mastery, prerequisite и цели |
| 2.2 | AI максимизирует обучение, а не выдаёт готовый код | `done` | `apps/api/app/mentor_prompts.py:5; apps/api/app/skill_evidence.py:235` | `tests/test_knowledge_check.py::test_hint_usage_is_server_derived_and_lowers_independent_score` | промпт запрещает solution, подсказки снижают independent |
| 2.3 | Структурированная память вместо истории сообщений | `partial` | `apps/api/app/db/models.py:388; apps/api/app/db/models.py:756` | `tests/test_mistake_memory.py::test_new_mistake_write_does_not_change_mastery_or_evidence` | нет interaction summary и behavioral memory |
| 2.4 | Gap analysis под реальную вакансию | `partial` | `apps/api/app/vacancies.py:71` | `tests/test_product_features.py::test_vacancy_extraction_keeps_exact_evidence_and_negation` | эвристика по reviewed alias, без числовых уровней |
| 2.5 | Цикл теория → проверка → практика → проект → review → проверка без подсказок | `partial` | `apps/api/app/learning.py:84; apps/api/app/reviews_api.py:487` | `tests/test_course_content_connectivity.py::test_each_active_lesson_has_exact_check_hint_ladder_and_published_version` | code review как шаг цикла отсутствует |

## §3. Позиционирование

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 3.1 | Тезис «наставник, который помнит ошибки» в интерфейсе | `partial` | `apps/web/app/page.tsx:1` | `нет` | лендинг описывает продукт, но не память ошибок |
| 3.2 | LLM — компонент системы, а не продукт; деградация без AI | `done` | `apps/api/app/learning.py:459; apps/api/app/main.py:73` | `tests/test_beginner_learning.py::test_course_orientation_explains_actual_unconfigured_tutor` | /learning/overview честно сообщает статус наставника |

## §4. Целевые аудитории

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 4.1 | Новичок: onboarding без диагностики, быстрый первый успех | `done` | `apps/api/app/beginner_content.py:1; apps/api/app/learning_plan.py:204` | `tests/test_beginner_learning.py::test_novice_starts_with_explanation_without_diagnostic_or_fabricated_evidence` | starter-план не создаёт AssessmentRun и evidence |
| 4.2 | Студент/junior/опытный: диагностика, code review, архитектура, growth plan | `partial` | `apps/api/app/assessment.py:152; apps/api/app/projects.py:129` | `tests/test_assessment.py::test_assessment_adapts_persists_and_completes` | code review кода ученика и growth plan не реализованы |

## §5. Основные доменные сущности

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 5.1 | User, Profile, Goal | `done` | `apps/api/app/db/models.py:34; apps/api/app/db/models.py:50; apps/api/app/db/models.py:64` | `tests/test_learning.py::test_auth_onboarding_csrf_and_validation` | goal хранит target_role, weekly_minutes, motivation |
| 5.2 | Skill, SkillEdge, UserSkill, SkillEvidence, Curriculum | `done` | `apps/api/app/db/models.py:753; apps/api/app/db/models.py:775; apps/api/app/skill_graph.py:25` | `tests/test_skill_graph.py::test_authored_graph_has_valid_references_and_acyclic_prerequisites` | граф валидируется при импорте |
| 5.3 | Exercise, Submission, TestCase, Hint | `done` | `apps/api/app/db/models.py:155; apps/api/app/db/models.py:182; apps/api/app/db/models.py:473` | `tests/test_submission_results_persistence.py::test_submission_results_keep_test_visibility_and_enforce_idempotency` | result хранит counts, но не источник hidden-тестов |
| 5.4 | Mistake, Misconception, Memory Record, Review, Tutor Thread, Subscription, Usage | `partial` | `apps/api/app/db/models.py:306; apps/api/app/db/models.py:388; apps/api/app/db/models.py:822` | `tests/test_mistake_memory_migration.py::test_mistake_memory_seed_is_idempotent_and_downgrade_removes_new_tables` | memory_records и Repository/CodeSymbol/CodeRelation/CodeFinding отсутствуют |

## §6. Основной пользовательский путь

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 6.1 | Регистрация email/password, сразу onboarding | `done` | `apps/api/app/auth.py:95` | `tests/test_auth.py::test_register_uses_opaque_cookies_and_requires_onboarding` | opaque cookie-сессия, onboarding_required=true |
| 6.2 | OAuth-вход | `missing` | `нет` | `нет` | только email/password; провайдеров OAuth нет |
| 6.3 | Выбор цели, недельного времени и самооценки как prior | `done` | `apps/api/app/auth.py:167; apps/api/app/assessment.py:145` | `tests/test_learning.py::test_auth_onboarding_csrf_and_validation` | experience_level задаёт стартовую сложность, но не итог |
| 6.4 | Адаптивная диагностика с пропуском очевидных тем | `done` | `apps/api/app/assessment.py:108` | `tests/test_assessment_bank.py::test_branch_never_repeats_a_question_or_a_skill_back_to_back` | шаг по authored difficulty slots |
| 6.5 | Построение Learning Path из цели, диагностики, prerequisite и вакансии | `done` | `apps/api/app/learning_plan.py:64; apps/api/app/curriculum.py:92` | `tests/test_learning_plan.py::test_plan_is_available_before_optional_assessment_and_is_owned` | план пересобирается после assessment и уроков |
| 6.6 | «Что мне делать сегодня»: конечная сессия 20–60 минут | `partial` | `apps/api/app/curriculum.py:160` | `tests/test_ai_domain_fixes.py::test_curriculum_durations_sum_to_planned_time_and_fit_real_budget` | сессия = min(60, weekly_minutes), нижняя граница 20 не гарантируется; dashboard показывает путь, а не сессию |

## §7. Skill Graph

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 7.1 | 80–150 навыков Python Backend | `done` | `apps/api/app/skill_graph.py:28` | `tests/test_skill_graph.py::test_authored_graph_has_valid_references_and_acyclic_prerequisites` | validate_graph требует 80..150 и ацикличность |
| 7.2 | Метаданные навыка: id, name, category, difficulty, prerequisites, importance, tags | `done` | `apps/api/app/skill_graph.py:6; apps/api/app/skill_graph.py:10` | `tests/test_skill_graph.py::test_authored_graph_has_valid_references_and_acyclic_prerequisites` | importance и tags выводятся детерминированно |
| 7.3 | Skill edges: prerequisite / related / specialization | `partial` | `apps/api/app/skill_graph.py:13; apps/api/app/skill_graph.py:31` | `tests/test_skill_graph.py::test_authored_graph_has_valid_references_and_acyclic_prerequisites` | relation валидируется, но заведены только prerequisite |

## §8. Модель mastery

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 8.1 | Раздельные измерения: knowledge, practice, independent, retention, confidence, evidence_count, next_review_at | `done` | `apps/api/app/db/models.py:756; apps/api/app/skill_evidence.py:539` | `tests/test_reviews_domain.py::test_review_is_retention_only_and_does_not_change_knowledge_projection` | review меняет только retention и расписание |
| 8.2 | independent_score: подсказки снижают самостоятельность | `done` | `apps/api/app/skill_evidence.py:235` | `tests/test_knowledge_check.py::test_hint_usage_is_server_derived_and_lowers_independent_score` | −20% за уровень, 5 подсказок → 0 |
| 8.3 | Каждое изменение mastery объясняется evidence и аудитом | `done` | `apps/api/app/skill_evidence.py:241; apps/api/app/skill_evidence.py:556` | `tests/test_skill_graph.py::test_skill_evidence_assistance_constraints_reject_invalid_pairs` | SkillMasteryAudit пишет before/after |
| 8.4 | Практика весит больше multiple choice | `partial` | `apps/api/app/skill_evidence.py:39` | `tests/test_runner_protocol.py::test_coding_result_becomes_server_attributed_evidence` | вес зависит от assistance, но не от типа источника |

## §9. Адаптивная диагностика

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 9.1 | Не статический тест на 100 вопросов: ограниченный бюджет | `done` | `apps/api/app/assessment.py:173; apps/api/app/assessment_content.py:1` | `tests/test_assessment_bank.py::test_early_stop_respects_max_questions` | MAX_QUESTIONS и детерминированный выбор |
| 9.2 | Метаданные вопроса (skill, difficulty, expected_time, prerequisites, answer_type, diagnostic value) и типы вопросов | `partial` | `apps/api/app/assessment_content.py:1` | `tests/test_assessment_bank.py::test_bank_covers_every_core_skill_at_least_once` | только multiple choice и code-сниппет; нет expected_time, answer_type, diagnostic value |
| 9.3 | Рост сложности при верных ответах и понижение при ошибке | `done` | `apps/api/app/assessment.py:138` | `tests/test_assessment_bank.py::test_correct_answer_raises_the_next_difficulty` | шаг по authored difficulty slot |
| 9.4 | Диагностика misconception при ошибке и откат к prerequisite | `partial` | `apps/api/app/mistake_memory.py:1` | `tests/test_mistake_memory.py::test_assessment_wrong_response_uses_only_its_exact_authored_mapping` | только authored mapping, автоматического вывода misconception нет |

## §10. Curriculum Engine

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 10.1 | Вход: цель, target skills, mastery, prerequisites, ошибки, forgetting, время, история, проекты, вакансия | `partial` | `apps/api/app/curriculum.py:92` | `tests/test_learning_plan.py::test_plan_recommendation_follows_progress_and_reassessment_updates_version` | проекты и явная история сессий не учитываются |
| 10.2 | Приоритет: importance × gap × readiness × forgetting × goal relevance | `partial` | `apps/api/app/curriculum.py:134` | `tests/test_ai_domain_fixes.py::test_curriculum_durations_sum_to_planned_time_and_fit_real_budget` | взвешенная сумма, а не произведение; веса объяснимы |
| 10.3 | Чередование новой темы, повторения и практики | `partial` | `apps/api/app/curriculum.py:172` | `tests/test_reviews_api.py::test_overdue_review_is_bounded_and_appended_after_learning_candidates` | review добавляется после уроков, практика как тип не выбирается |

## §11. Vacancy → индивидуальный roadmap

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 11.1 | Pipeline: текст → requirement extractor → normalized requirements → mapping to Skill Graph | `partial` | `apps/api/app/vacancies.py:71` | `tests/test_product_features.py::test_vacancy_extraction_keeps_exact_evidence_and_negation` | нормализация — reviewed alias, не отдельный extractor |
| 11.2 | Не только keywords: уровень требования и подтверждающий фрагмент | `partial` | `apps/api/app/vacancies.py:82` | `tests/test_product_features.py::test_vacancy_extraction_keeps_exact_evidence_and_negation` | уровень required/preferred/mentioned + evidence-предложение |
| 11.3 | Два профиля «требуется»/«умею» и порядок обучения по gap | `partial` | `apps/api/app/vacancies.py:106` | `tests/test_product_features.py::test_vacancy_history_gap_target_and_ownership` | gap считается от 0.75, часть навыков not_assessed |
| 11.4 | Проценты — ориентир, а не вероятность трудоустройства | `partial` | `apps/api/app/vacancies.py:140` | `tests/test_product_features.py::test_vacancy_history_gap_target_and_ownership` | проценты не показываются вовсе, есть notice |
| 11.5 | URL вакансии — только источник, сервер не фетчит произвольный URL | `done` | `apps/api/app/vacancies.py:43` | `tests/test_product_features.py::test_vacancy_extraction_keeps_exact_evidence_and_negation` | принимается только публичный https URL без credentials |

## §12. Learning Session

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 12.1 | Конечная сессия на 20–60 минут с составом и временем | `partial` | `apps/api/app/curriculum.py:232` | `tests/test_ai_domain_fixes.py::test_curriculum_durations_sum_to_planned_time_and_fit_real_budget` | состав и минуты есть, нижняя граница 20 не enforced |
| 12.2 | Структура урока: зачем, prerequisites, объяснение, пример, checkpoint, misconception, практика, вывод, review | `done` | `apps/api/app/learning.py:84; apps/api/app/learning_content.py:1` | `tests/test_course_content_connectivity.py::test_each_active_lesson_has_exact_check_hint_ladder_and_published_version` | все поля отдаются в LessonResponse |
| 12.3 | Review scheduling после урока | `done` | `apps/api/app/skill_evidence.py:537; apps/api/app/reviews_api.py:285` | `tests/test_reviews_api.py::test_review_api_is_owned_csrf_protected_and_server_graded` | next_review_at пишется в той же транзакции |
| 12.4 | Психологически проще: «продолжить урок», а не каталог | `partial` | `apps/web/app/learning/course-path.tsx:79` | `нет` | один next-lesson CTA, но нет таймера сессии и «сегодня 40 минут» |

## §13. Система подсказок

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 13.1 | Уровни 0–5 и полное решение | `partial` | `apps/api/app/exercise_hints.py:274; apps/api/app/exercise_hints.py:359` | `tests/test_learning.py::test_hint_ladder_reveals_one_next_level_and_is_append_only` | 5 уровней, уровень 5 — разбор-решение; отдельного полного solution нет |
| 13.2 | Использование подсказок влияет на independent mastery | `done` | `apps/api/app/skill_evidence.py:235` | `tests/test_knowledge_check.py::test_hint_usage_is_server_derived_and_lowers_independent_score` | assistance выводится из HintReveal, не от клиента |
| 13.3 | Просмотр solution ⇒ задача не доказательство владения | `done` | `apps/api/app/skill_evidence.py:235` | `tests/test_knowledge_check.py::test_hint_usage_is_server_derived_and_lowers_independent_score` | 5 уровней дают нулевой independent credit |
| 13.4 | Позже похожая задача без подсказки | `partial` | `apps/api/app/reviews_api.py:285` | `tests/test_reviews_api.py::test_today_contract_is_public_and_replays_without_duplicate_evidence` | повтор — authored вопросы того же урока, не новая задача |

## §14. Practice Engine

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 14.1 | Форматы: predict output, fill code, implement function, debug, refactor, tests, SQL, API design, explain, mini project, ADR | `partial` | `apps/api/app/practice_catalog.py:1; apps/api/app/reflections_api.py:53` | `tests/test_completed_course.py::test_all_graph_skills_have_valid_lesson_and_trusted_practice` | реально: function + quiz + письменная рефлексия |
| 14.2 | Тематические интересы пользователя (игры, финансы, спорт) | `missing` | `нет` | `нет` | интересы не собираются и не влияют на обёртку задачи |

## §15. Project System

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 15.1 | Шаблоны проектов Python Backend | `done` | `apps/api/app/projects.py:30` | `tests/test_product_features.py::test_projects_idempotency_validation_and_private_portfolio` | 9 шаблонов от CLI до final-backend |
| 15.2 | Milestones и проверка комплектности артефакта | `done` | `apps/api/app/projects.py:166` | `tests/test_product_features.py::test_projects_idempotency_validation_and_private_portfolio` | проверяются обязательные разделы, код не исполняется |
| 15.3 | Portfolio evidence page: stack, skills, tests, GitHub, объяснение | `partial` | `apps/api/app/projects.py:197` | `tests/test_product_features.py::test_projects_idempotency_validation_and_private_portfolio` | только title/summary/repo, без stack, tests и скиллов |
| 15.4 | Пользовательское объяснение проекта | `missing` | `нет` | `нет` | поля объяснения в модели портфолио нет |

## §16. Knowledge Base и RAG

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 16.1 | Источники KB: свои материалы, официальная документация, curated examples, ошибки, задачи, specs, rubrics | `partial` | `apps/api/app/knowledge_base.py:35` | `tests/test_knowledge_base.py::test_indexing_is_scoped_to_skill_and_version` | индексируется только авторская теория урока |
| 16.2 | Pipeline: authoring → normalization → chunking → metadata → embeddings | `done` | `apps/api/app/knowledge_base.py:78; apps/api/app/knowledge_base.py:132` | `tests/test_knowledge_base.py::test_indexing_is_scoped_to_skill_and_version` | чанки идемпотентны, переиндексация только изменённого |
| 16.3 | Metadata-фильтр по skill и версии; pgvector/HNSW/IVFFlat | `partial` | `apps/api/app/knowledge_base.py:232; apps/api/app/db/models.py:996` | `tests/test_knowledge_base.py::test_retrieval_never_returns_another_skill_or_version` | pgvector нет: LargeBinary + cosine в домене (ADR) |
| 16.4 | Semantic + full-text + rerank | `missing` | `нет` | `нет` | только cosine по одному вектору, без hybrid и rerank |
| 16.5 | Не отправлять весь курс: top-k и бюджет контекста | `done` | `apps/api/app/knowledge_base.py:50; apps/api/app/knowledge_base.py:303` | `tests/test_knowledge_base.py::test_retrieval_budget_is_capped` | 2 чанка, 2400 символов |

## §17. Long-term Memory

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 17.1 | Profile Memory: цель, опыт, стек, язык, время, интересы, стиль, target vacancy | `partial` | `apps/api/app/db/models.py:50; apps/api/app/db/models.py:64` | `tests/test_learning.py::test_auth_onboarding_csrf_and_validation` | нет языка, стиля объяснений и интересов; стек фиксирован |
| 17.2 | Skill Memory: структурированное mastery по навыку | `done` | `apps/api/app/db/models.py:756` | `tests/test_skill_graph.py::test_mastery_fallback_is_consistent_across_path_plan_and_curriculum` | UserSkill — проекция evidence |
| 17.3 | Mistake Memory: тип, описание, first/last seen, count | `partial` | `apps/api/app/db/models.py:388` | `tests/test_mistake_memory.py::test_distinct_mapped_mistakes_increment_but_reprocessing_is_idempotent` | нет resolved-статуса; описание берётся из MisconceptionVersion, category/fingerprint отсутствуют |
| 17.4 | Misconception Memory: отличие механической ошибки от неверной модели | `partial` | `apps/api/app/db/models.py:306; apps/api/app/db/models.py:351` | `tests/test_mistake_memory.py::test_assessment_wrong_response_uses_only_its_exact_authored_mapping` | только authored misconception versions, авто-извлечения нет |
| 17.5 | Interaction Summary и Behavioral Memory | `missing` | `нет` | `нет` | сводок сессий и поведенческих сигналов нет |

## §18. Spaced Repetition

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 18.1 | next_review_at для skill/concept | `done` | `apps/api/app/db/models.py:756; apps/api/app/skill_evidence.py:537` | `tests/test_reviews_domain.py::test_review_policy_uses_conservative_explainable_intervals` | дата пересчитывается только при применённом review |
| 18.2 | Интервалы: incorrect→1, hard→2, hint→3–4, independent→7, repeated→14/30/60 | `partial` | `apps/api/app/reviews.py:24; apps/api/app/reviews.py:58` | `tests/test_reviews_domain.py::test_review_policy_covers_all_supported_intervals` | 1/3/7/14/30/60; категории hard (2 дня) нет |
| 18.3 | Daily plan смешивает новую тему и review, возвращает забытое | `partial` | `apps/api/app/curriculum.py:165` | `tests/test_reviews_api.py::test_overdue_review_is_bounded_and_appended_after_learning_candidates` | review идёт после уроков и ограничен приоритетом 0.30 |

## §19. Tutor Engine

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 19.1 | Context packet: goal, topic, mastery, mistakes, exercise, knowledge, hint_level, mode, allowed_behavior | `partial` | `apps/api/app/mentor.py:225; apps/api/app/mentor_prompts.py:24` | `tests/test_mentor.py::test_success_history_retry_and_evidence` | есть урок, уровень, история, ошибки, RAG; нет goal/mastery/hint_level/mode |
| 19.2 | Режимы Teach, Socratic, Hint, Debug Coach, Review, Examiner, Interviewer, Project Mentor | `done` | `apps/api/app/tutor_modes.py:1; apps/api/app/mentor_prompts.py:24` | `tests/test_tutor_modes.py::test_catalogue_exposes_eight_modes; tests/test_tutor_modes.py::test_explicit_mode_reaches_the_provider_and_is_stored; tests/test_tutor_modes.py::test_every_mode_keeps_the_trusted_base_rules` | восемь режимов как блоки правил поверх доверенного промпта; выбор явный или серверный, режим пишется в сообщение и в ответ API |
| 19.3 | Tutor знает про оцениваемое задание и работает как orchestrator, а не один prompt | `partial` | `apps/api/app/mentor_prompts.py:9; apps/api/app/mentor.py:186` | `tests/test_mentor.py::test_success_records_usage_with_safe_token_types_and_character_counts` | оркестрация admission/RAG/usage есть; проверки утечки solution нет |

## §20. AI Provider Layer

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 20.1 | Абстракция LLMProvider: generate / structured / embed | `partial` | `apps/api/app/ai_gateway.py:57; apps/api/app/ai_embeddings.py:83` | `tests/test_ai_admission.py::test_daily_shared_budget_reserves_pending_calls_and_requires_configuration` | функциональный адаптер, не класс с реализациями |
| 20.2 | Model routing: cheap для классификации/памяти, strong для review/roadmap | `partial` | `apps/api/app/ai_curriculum.py:23; model-routing.example.json:1` | `нет` | только model_override для curriculum; роутера ролей нет |
| 20.3 | Gateway: routing, accounting, timeouts, retries, fallback, caching, logging, prompt versioning, structured validation | `partial` | `apps/api/app/ai_gateway.py:62` | `tests/test_ai_admission.py::test_exact_money_requires_model_price_and_complete_integer_provider_usage` | есть timeout, лимит ответа, usage; retries/fallback/cache сознательно отсутствуют (ADR) |

## §21. Prompt Registry

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 21.1 | Промпты централизованы, а не hardcoded по backend | `partial` | `apps/api/app/mentor_prompts.py:1; apps/api/app/ai_curriculum.py:201` | `tests/test_mentor.py::test_missing_config_and_access` | два реестра; остальные строки в коде |
| 21.2 | Метаданные: version, model policy, parameters, output schema, eval score, changelog | `partial` | `apps/api/app/mentor_prompts.py:4; apps/api/app/ai_curriculum.py:24` | `нет` | есть версии и schema, нет eval score и changelog |
| 21.3 | A/B или staged rollout промптов | `missing` | `нет` | `нет` | механизма выбора версии промпта нет |

## §22. Structured Outputs

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 22.1 | Внутренние AI-задачи возвращают JSON по schema | `done` | `apps/api/app/ai_curriculum.py:95; apps/api/app/ai_curriculum.py:297` | `tests/test_ai_domain_fixes.py::test_curriculum_durations_sum_to_planned_time_and_fit_real_budget` | GeneratedOutput с extra=forbid |
| 22.2 | Валидация до использования, а не regex-парсинг | `done` | `apps/api/app/ai_curriculum.py:218` | `tests/test_ai_domain_fixes.py::test_ai_allowlist_requires_transitive_prerequisites` | доменная валидация skill_id и бюджета |

## §23. Как сделать AI менее «глупым»

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 23.1 | Качественный context и verified knowledge | `done` | `apps/api/app/knowledge_base.py:303; apps/api/app/mentor_prompts.py:24` | `tests/test_knowledge_base.py::test_retrieval_never_returns_another_skill_or_version` | только теория текущего навыка и версии |
| 23.2 | Deterministic tools, execution tests, static analyzers | `partial` | `apps/runner/runner_worker/execution.py:10` | `tests/test_runner_protocol.py::test_coding_result_becomes_server_attributed_evidence` | тесты есть, static analyzers нет |
| 23.3 | Объективный test result важнее мнения LLM | `done` | `apps/api/app/skill_evidence.py:100` | `tests/test_runner_protocol.py::test_malformed_terminal_result_is_fail_closed` | score выводится только из tests_passed/total |
| 23.4 | Confidence handling | `partial` | `apps/api/app/skill_evidence.py:554` | `нет` | confidence = вес evidence / 5, без калибровки |

## §24. AI Evaluation Framework

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 24.1 | Benchmark из реальных кейсов до запуска | `missing` | `docs/eval/tasks.md:1` | `нет` | только ручной список задач, harness отсутствует |
| 24.2 | Rubric на кейс и повторный прогон при смене модели/prompt | `missing` | `docs/eval/tasks.md:5` | `нет` | оценка 0–2 вручную, автоматизации нет |
| 24.3 | AI-метрики: correctness, usefulness, hallucination, leakage, memory, latency, cost | `missing` | `нет` | `нет` | метрик качества AI нет |

## §25. Web App как основной интерфейс

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 25.1 | Разделы /auth, /onboarding, /dashboard, /learn, /practice, /projects, /tutor, /vacancies, /profile, /settings | `partial` | `apps/web/app/auth/page.tsx:1; apps/web/app/learning/page.tsx:1` | `нет` | есть auth, onboarding, dashboard, learning, projects, account, billing; нет /tutor, /vacancies, /settings |
| 25.2 | Next.js / React / TypeScript | `partial` | `apps/web/package.json:1` | `нет` | стек есть; pytest-теста нет, только browser smoke в CI |
| 25.3 | Separation of concerns: страница грузит данные, доменные компоненты рендерят | `partial` | `apps/web/app/learning/page.tsx:1; docs/decisions.md:1` | `нет` | разделение по ADR, автотеста структуры нет |

## §26. Dashboard

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 26.1 | Главный вопрос «что мне делать сейчас» + сессия | `partial` | `apps/web/app/dashboard/page.tsx:1; apps/web/app/learning/course-path.tsx:79` | `нет` | есть next lesson, нет сессии на 20–60 минут |
| 26.2 | Цель, progress, слабые навыки, streak, recurring mistakes, проект — без перегруза | `partial` | `apps/web/app/dashboard/page.tsx:100` | `нет` | есть цель и ритм; нет streak, recurring mistakes и проекта |

## §27. Code Editor

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 27.1 | Полноценный браузерный редактор Monaco | `out-of-scope` | `apps/web/app/learning/code-editor.tsx:1` | `нет` | ADR decisions.md: CodeMirror 6 вместо Monaco (вес, SSR, одна страница) |
| 27.2 | Autosave и панели: debounce, server draft, local fallback, version, console, tests panel, diff, reset, snapshots | `partial` | `apps/web/app/learning/coding-practice.tsx:74` | `нет` | только localStorage с ключом версии и панель результата; server draft, diff, snapshots, revert отсутствуют |
| 27.3 | Подсказки в редакторе | `partial` | `apps/web/app/learning/hint-ladder.tsx:1` | `tests/test_learning.py::test_hint_ladder_reveals_one_next_level_and_is_append_only` | UI не покрыт тестом, API покрыт |

## §28. Mobile и PWA

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 28.1 | PWA installable experience | `missing` | `нет` | `нет` | manifest и service worker отсутствуют |
| 28.2 | Mobile: теория, quiz, flashcards, короткие правки, чат, roadmap | `partial` | `apps/web/app/globals.css:1` | `нет` | адаптивная вёрстка есть, flashcards и PWA нет |
| 28.3 | Сообщение «задание удобнее продолжить на компьютере» | `missing` | `нет` | `нет` | ограничения мобильного редактора не сообщаются |

## §29. Telegram Bot

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 29.1 | Привязка аккаунта одноразовым токеном | `done` | `apps/api/app/accounts_api.py:212; apps/api/app/notifications.py:80` | `tests/test_account_services.py::test_preferences_and_telegram_binding_require_csrf_secret_ownership_and_one_use` | TTL 15 минут, single-use |
| 29.2 | Daily reminder, review cards и deep link в desktop task | `partial` | `apps/api/app/notifications.py:93` | `tests/test_account_services.py::test_outbox_preferences_and_idempotency_prevent_unwanted_delivery` | текст-напоминание без карточек, тем и ссылок |
| 29.3 | Quick quiz, streak, weekly summary | `missing` | `нет` | `нет` | ни quiz, ни streak, ни weekly summary в боте нет |
| 29.4 | Tutor chat | `done` | `apps/api/app/notifications.py:259; apps/api/app/accounts_api.py:245` | `tests/test_completed_course.py::test_telegram_questions_enqueue_once_without_sending_messages` | ответ сохраняется до отправки, без выдуманного mastery |
| 29.5 | Один backend и одна память у сайта и бота | `done` | `apps/api/app/notifications.py:245` | `tests/test_completed_course.py::test_telegram_questions_enqueue_once_without_sending_messages` | бот пишет в те же таблицы через сервис |

## §30. Backend: modular monolith

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 30.1 | Modular monolith без микросервисов | `done` | `apps/api/app/main.py:42; docs/decisions.md:5` | `tests/test_observability_contracts.py::test_api_never_imports_the_execution_host; tests/test_observability_contracts.py::test_runner_never_imports_the_application` | один процесс API и отдельный процесс runner; импорт через границу запрещён и проверяется разбором AST |
| 30.2 | Модули auth/users/goals/skills/courses/assessments/roadmap/learning/exercises/submissions/tutor/memory/execution/repositories/billing/notifications | `partial` | `apps/api/app/` | `нет` | repositories отсутствует; модули файлами, а не пакетами |
| 30.3 | Stack FastAPI, SQLAlchemy, Alembic, PostgreSQL, Pydantic, Redis, Celery | `partial` | `apps/api/requirements.lock:1` | `tests/test_health.py::test_health_returns_api_and_database_status` | Redis/Celery не используются: очередь и лимиты на БД |

## §31. PostgreSQL — базовая схема

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 31.1 | Базовые таблицы users…ai_usage | `partial` | `apps/api/migrations/versions/0001_initial.py:1` | `tests/test_learning_migration.py::test_upgrade_preserves_users_and_downgrade` | 37 миграций; repository_* таблиц нет |
| 31.2 | user_skills с восемью измерениями | `done` | `apps/api/app/db/models.py:756` | `tests/test_skill_graph.py::test_skill_evidence_assistance_constraints_reject_invalid_pairs` | ограничения на assisted/hint_count в БД |
| 31.3 | mistakes: category, fingerprint, misconception, resolved_at | `partial` | `apps/api/app/db/models.py:388` | `tests/test_mistake_memory.py::test_distinct_mapped_mistakes_increment_but_reprocessing_is_idempotent` | fingerprint, category и resolved_at отсутствуют |
| 31.4 | knowledge_chunks: source_id, metadata jsonb, embedding vector, version | `partial` | `apps/api/app/db/models.py:996` | `tests/test_knowledge_base_migration.py::test_knowledge_chunk_migration_roundtrip_preserves_existing_data` | нет source_id/metadata jsonb; embedding — LargeBinary (ADR) |

## §32. AI usage accounting

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 32.1 | Запись usage: user, feature, provider, model, tokens, cost, latency | `partial` | `apps/api/app/db/models.py:647; apps/api/app/mentor.py:62` | `tests/test_mentor.py::test_success_records_usage_with_safe_token_types_and_character_counts` | нет provider и latency_ms |
| 32.2 | Budget guards: per-user daily, per-feature cap, global monthly cap | `partial` | `apps/api/app/ai_admission.py:1` | `tests/test_ai_admission.py::test_daily_shared_budget_reserves_pending_calls_and_requires_configuration` | дневной и per-feature есть; глобального месячного cap нет |
| 32.3 | Alerts на аномалию расхода | `missing` | `нет` | `нет` | алертов и anomaly-детекции нет |

## §33. API skeleton

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 33.1 | POST /auth/register, /auth/login, /auth/logout, GET /me, PATCH /me/profile | `done` | `apps/api/app/auth.py:95; apps/api/app/auth.py:132` | `tests/test_auth.py::test_login_logout_and_invalid_password` | пути совпадают со спекой |
| 33.2 | Assessment: start / answer / result | `partial` | `apps/api/app/assessment.py:152; apps/api/app/assessment.py:223` | `tests/test_assessment.py::test_assessment_adapts_persists_and_completes` | GET /assessment и POST /answers; отдельных start/result нет |
| 33.3 | Vacancy analyze, learning-path current/recalculate | `partial` | `apps/api/app/vacancies.py:143; apps/api/app/learning_plan_api.py:11` | `tests/test_product_features.py::test_vacancy_history_gap_target_and_ownership` | есть /vacancies и /learning/plan; recalculate нет, есть /curriculum/refresh |
| 33.4 | Sessions today/start/complete, lessons/{id}, submissions, code/run | `partial` | `apps/api/app/reviews_api.py:285; apps/api/app/practice.py:211; apps/api/app/jobs_api.py:77` | `tests/test_practice.py::test_runner_unavailable_configuration_stays_fail_closed` | сессий как сущности и /code/run нет; submission = attempt/job |
| 33.5 | Tutor messages | `partial` | `apps/api/app/mentor.py:186` | `tests/test_mentor.py::test_success_history_retry_and_evidence` | POST /learning/lessons/{id}/chat вместо /tutor/messages |
| 33.6 | Repositories import/status/review | `missing` | `нет` | `нет` | repository API отсутствует |
| 33.7 | Long-running job возвращает job ID и обрабатывается асинхронно | `done` | `apps/api/app/jobs_api.py:77; apps/api/app/jobs.py:1` | `tests/test_completed_course.py::test_coding_specification_hides_keys_and_jobs_are_idempotent_without_runner` | 202 + Location, durable очередь |

## §34. Async Jobs и Redis

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 34.1 | Очередь: sandbox jobs, notifications, scheduled reviews, embeddings, repository ingestion, weekly report | `partial` | `apps/api/app/jobs_api.py:1; apps/api/app/notifications.py:93` | `tests/test_completed_course.py::test_coding_specification_hides_keys_and_jobs_are_idempotent_without_runner` | есть jobs и notifications; repository и weekly report отсутствуют |
| 34.2 | Redis для queue, cache, rate limits, locks | `missing` | `нет` | `нет` | Redis не подключён, очередь и throttle на БД |
| 34.3 | Критические данные не только в Redis | `done` | `apps/api/app/ai_admission.py:1` | `tests/test_ai_admission.py::test_pending_lease_blocks_duplicate_and_expired_worker_cannot_publish` | аренды и лимиты durable в PostgreSQL |

## §35. Code Execution Architecture

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 35.1 | Код не исполняется в процессе API | `done` | `apps/api/app/runner.py:1; apps/api/app/practice.py:252` | `tests/test_practice.py::test_runner_unavailable_configuration_stays_fail_closed` | RunnerUnavailable, статус unavailable |
| 35.2 | Каждый запуск — отдельная короткоживущая среда | `done` | `apps/runner/runner_worker/execution.py:39` | `tests/runner/tests/test_worker.py::WorkerTests::test_runtime_cleanup_runs_when_cli_wait_times_out` | контейнер удаляется, cleanup подтверждается |
| 35.3 | Лимиты: memory, CPU, wall-clock, PID, FS, network off, non-root, ro FS, tmp, no host mounts, no docker socket, no env, seccomp | `done` | `apps/runner/runner_worker/policy.py:155; apps/runner/runner_worker/sandbox_landlock.py:1` | `tests/runner/tests/test_landlock_sandbox.py::LandlockSandboxTests::test_memory_bomb_is_a_resource_violation` | docker create: network none, read-only, uid 65532, cap-drop ALL, pids 32, cpus 1, memory 512m |
| 35.4 | Этапы зрелости sandbox: alpha/beta/growth | `partial` | `docs/runner-deployment.md:1` | `нет` | описано; развёртывание на целевом host не выполнялось |
| 35.5 | Компрометация runner не даёт доступ к БД, secrets и AI keys | `done` | `apps/runner/runner_worker/policy.py:1; apps/runner/runner_worker/server.py:1` | `tests/runner/tests/test_landlock_sandbox.py::LandlockSandboxTests::test_no_environment_secrets_are_visible` | отдельный host, mTLS, нет env API |

## §36. Python Runner

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 36.1 | Base environment: Python, pytest, ruff, mypy | `partial` | `apps/runner/Sandbox.Dockerfile:1` | `нет` | pytest и ruff есть; mypy нет |
| 36.2 | Pipeline: validate → sandbox → compile → public → hidden → lint → capture → limits → destroy → save | `partial` | `apps/runner/runner_worker/execution.py:10; apps/runner/runner_worker/server.py:14` | `tests/runner/tests/test_server_mtls.py::RunnerServiceTests::test_reference_solution_passes_every_case` | нет lint/static шага |
| 36.3 | Normalized result: status, exit_code, stdout, stderr, tests, timeout, resource_violation, static_findings | `partial` | `apps/api/app/runner.py:41` | `tests/test_runner_protocol.py::test_worker_result_contract_is_normalized_and_persisted` | static_findings отсутствует |
| 36.4 | Public и hidden tests; источник hidden не передаётся | `done` | `apps/api/app/runner_exercise_content.py:1; apps/runner/runner_worker/execution.py:12` | `tests/test_runner_protocol.py::test_public_hidden_results_expose_counts_not_sources` | worker получает кейсы, клиент — только counts |

## §37. JavaScript / TypeScript Runner

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 37.1 | JavaScript/TypeScript runner: Node, tsc, ESLint, Vitest/Jest, package allowlist, без произвольного npm install | `out-of-scope` | `нет` | `нет` | спец. §90 и UNIMPLEMENTED_STAGES: вне Python MVP |

## §38. C++ Runner

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 38.1 | C++ runner: compile, warnings, clang-tidy, sanitizers, unit tests, CPU/memory/time limits | `out-of-scope` | `нет` | `нет` | спец. §90: C++ вне MVP |

## §39. HTML/CSS/React

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 39.1 | HTML/CSS/React: editor + live preview в sandboxed iframe | `out-of-scope` | `нет` | `нет` | спец. §90: React live IDE вне MVP |

## §40. Hidden tests и rubric

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 40.1 | Public и hidden tests, source hidden не передаётся пользователю | `done` | `apps/api/app/runner_exercise_content.py:1` | `tests/test_runner_protocol.py::test_public_hidden_results_expose_counts_not_sources` | визибилити хранится на кейсе |
| 40.2 | Rubric: correctness 50, readability 15, edge cases 10, testing 10, complexity 10, style 5 | `done` | `apps/api/app/rubric.py:1` | `tests/test_code_review.py::test_endpoint_scores_by_level_and_stores_the_review` | шесть критериев 0–2, взвешенный итог считает сервер; ревью сохраняется с моделью и уровнем |
| 40.3 | Вес rubric зависит от уровня пользователя | `done` | `apps/api/app/rubric.py:33` | `tests/test_code_review.py::test_weights_follow_the_level_and_sum_to_one_hundred` | веса по уровню: beginner 60/20/10/5/0/5, advanced 40/10/15/15/10/10, сумма всегда 100 |
| 40.4 | LLM получает task, test results, linter output, уровень, ошибки и rubric | `done` | `apps/api/app/rubric.py:118` | `tests/test_code_review.py::test_model_total_is_ignored_and_score_is_computed_here` | итог модели игнорируется: балл считается из оценок и весов на сервере |

## §41. Data flow одного submission

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 41.1 | Draft → Run/Submit → submission record → execution queue → результат | `done` | `apps/web/app/learning/coding-practice.tsx:74; apps/api/app/practice.py:211; apps/api/app/jobs_api.py:77` | `tests/test_practice.py::test_attempt_auth_csrf_and_owned_history` | draft локальный, запись и job создаются сервером |
| 41.2 | Static findings, tutor feedback, memory extractor, mastery update, review scheduling | `partial` | `apps/api/app/skill_evidence.py:578` | `tests/test_runner_protocol.py::test_coding_result_becomes_server_attributed_evidence` | mastery и result атомарны; findings, AI-feedback и extractor по коду отсутствуют |

## §42. Большие репозитории 5–30k+ строк

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 42.1 | Code Intelligence Pipeline: ingestion → file classification → parsing → symbols → dependency graph → summaries → index | `out-of-scope` | `нет` | `нет` | спец. §90: полный large-repository engine вне MVP |

## §43. Tree-sitter и parsing

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 43.1 | Tree-sitter: modules, classes, functions, imports, calls, ranges | `out-of-scope` | `нет` | `нет` | спец. §90; tree-sitter в зависимостях отсутствует |

## §44. Repository schema

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 44.1 | Схема repositories / repository_files / code_symbols / symbol_relations / chunks / summaries / findings / runs | `out-of-scope` | `нет` | `нет` | спец. §90: repository-слоя нет |

## §45. Repository filtering

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 45.1 | Фильтрация vendor/generated/build, .gitignore, лимиты размера/количества, language allowlist | `out-of-scope` | `нет` | `нет` | спец. §90: загрузок репозиториев нет |

## §46. Hierarchical summaries

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 46.1 | Hierarchical summaries function → class → file → module → repository, инкрементальный пересчёт | `out-of-scope` | `нет` | `нет` | спец. §90 |

## §47. Repository retrieval

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 47.1 | Repository retrieval по semantic similarity, символам, stack trace и графу зависимостей | `out-of-scope` | `нет` | `нет` | спец. §90 |

## §48. Большой Code Review — multi-pass

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 48.1 | Шесть проходов: structure, correctness, maintainability, testing, security, educational synthesis | `out-of-scope` | `нет` | `нет` | спец. §90: deep review репозитория вне MVP |

## §49. Code Review как обучение

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 49.1 | Socratic review кода ученика с вопросом вместо переписанного решения | `done` | `apps/api/app/code_review_api.py:34` | `tests/test_code_review.py::test_rubric_endpoint_lists_all_weights` | GET /learning/rubric отдаёт критерии, веса по уровням и порог прохождения |

## §50. Recurring Mistake Detection

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 50.1 | Классификация category, привязка к skill и fingerprint | `partial` | `apps/api/app/mistake_memory.py:1` | `tests/test_mistake_memory.py::test_distinct_mapped_mistakes_increment_but_reprocessing_is_idempotent` | category и fingerprint отсутствуют, mapping authored |
| 50.2 | Поиск похожих ошибок и рост recurrence | `done` | `apps/api/app/db/models.py:388` | `tests/test_mistake_memory.py::test_distinct_mapped_mistakes_increment_but_reprocessing_is_idempotent` | occurrence_count растёт, повторная обработка идемпотентна |
| 50.3 | Misconception и scheduled review по ошибке; tutor упоминает прошлую ошибку только при evidence | `partial` | `apps/api/app/mentor.py:234` | `tests/test_mentor.py::test_success_history_retry_and_evidence` | tutor видит только authored-сигналы; review от ошибки не назначается |

## §51. Secret Detection

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 51.1 | Поиск API keys, private keys, passwords, tokens, .env при загрузке; redaction, предупреждение, rotation | `missing` | `нет` | `нет` | сканирования секретов нет, загрузок репозитория тоже |

## §52. Prompt Injection из кода

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 52.1 | Недоверенный контент явно маркируется как untrusted data | `done` | `apps/api/app/knowledge_base.py:332; apps/api/app/mentor_prompts.py:14` | `tests/test_knowledge_base.py::test_retrieved_text_is_labelled_untrusted_data_not_instructions` | JSON-поле content с явной пометкой |
| 52.2 | System/developer rules отделены от data; внешние источники так же | `done` | `apps/api/app/mentor_prompts.py:5` | `tests/test_knowledge_base.py::test_retrieved_text_is_labelled_untrusted_data_not_instructions` | system prompt вне пользовательского контента |

## §53. Auth и sessions

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 53.1 | Secure httpOnly cookies и CSRF на изменяющих запросах | `done` | `apps/api/app/auth.py:42; apps/api/app/auth.py:87` | `tests/test_auth.py::test_profile_update_is_csrf_protected` | CSRF-cookie + X-CSRF-Token |
| 53.2 | Refresh token rotation | `partial` | `apps/api/app/auth.py:114` | `tests/test_auth.py::test_login_logout_and_invalid_password` | refresh-токенов нет; повторный login отзывает прошлую сессию |
| 53.3 | OAuth state verification | `missing` | `нет` | `нет` | OAuth не реализован |
| 53.4 | Argon2id, email verification, single-use reset tokens | `done` | `apps/api/app/security.py:18; apps/api/app/accounts_api.py:79` | `tests/test_account_services.py::test_verification_is_single_use_and_never_stores_raw_token_in_token_table` | scrypt-фолбэк только для офлайн-тестов |

## §54. Telegram linking

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 54.1 | Одноразовый short-lived token через deep link | `done` | `apps/api/app/accounts_api.py:212; apps/api/app/notifications.py:80` | `tests/test_account_services.py::test_preferences_and_telegram_binding_require_csrf_secret_ownership_and_one_use` | TTL 15 минут, consume_token с CAS |
| 54.2 | Не связывать по username | `done` | `apps/api/app/db/account_models.py:39` | `tests/test_account_services.py::test_preferences_and_telegram_binding_require_csrf_secret_ownership_and_one_use` | хранится chat_id, не username |

## §55. Permissions

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 55.1 | Роли user/content_editor/reviewer/support/admin; least privilege и audit чувствительных действий | `partial` | `apps/api/app/accounts_api.py:310; apps/api/app/db/account_models.py:90` | `tests/test_account_services.py::test_admin_role_is_server_allowlisted_and_actions_are_audited` | есть allowlist ADMIN_USER_IDS и AdminAudit; ролей и UI нет |

## §56. Privacy

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 56.1 | Что и сколько хранится, что уходит провайдеру, удаление derived embeddings и summaries | `partial` | `apps/api/app/account_services.py:1; docs/decisions.md:60` | `tests/test_account_services.py::test_export_and_transactional_delete_include_derived_rows_and_preserve_other_user` | удаление покрывает существующие таблицы; политики хранения и embeddings-каскада для repo нет |
| 56.2 | Публичное портфолио включается только явно; repository по умолчанию private | `partial` | `apps/api/app/projects.py:197` | `tests/test_product_features.py::test_projects_idempotency_validation_and_private_portfolio` | портфолио opt-in; repository-функции нет |

## §57. Delete Account

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 57.1 | Удаление профиля, сообщений, submissions, личной учебной памяти и storage | `done` | `apps/api/app/account_services.py:1` | `tests/test_account_services.py::test_export_and_transactional_delete_include_derived_rows_and_preserve_other_user` | обходит FK-детей и derived-строки |
| 57.2 | Удаление repository files, embeddings и summaries | `out-of-scope` | `нет` | `нет` | repository-слоя нет (§90); embeddings уроков — авторские, не пользовательские |

## §58. Контент и авторские права

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 58.1 | Только собственный и разрешённый контент, оригинальные упражнения | `partial` | `apps/api/app/learning_content.py:1` | `нет` | контент авторский, но лицензионных метаданных нет |
| 58.2 | Human review критического учебного ядра | `partial` | `docs/prompts/06-course-content.md:1` | `нет` | процесс описан в docs, workflow ревью в системе отсутствует |

## §59. Content CMS

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 59.1 | Статусы draft / review / published / archived | `partial` | `apps/api/app/content_publication.py:1; apps/api/app/db/models.py:284` | `tests/test_exercise_snapshots.py::test_new_lesson_checks_and_hints_publish_as_immutable_schema_two_snapshot` | есть immutable published-версии; draft/review/archived как состояния нет |
| 59.2 | Versioning и rollback контента | `partial` | `apps/api/app/exercise_snapshots.py:1` | `tests/test_learning_migration.py::test_exercise_content_snapshot_roundtrip_0016_head_0016_head` | версии неизменяемы, rollback-эндпоинта нет |

## §60. Course Versioning

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 60.1 | Пользователь не теряет старый путь при смене curriculum | `done` | `apps/api/app/learning_continuity.py:1; apps/api/app/content_publication.py:1` | `tests/test_beginner_learning.py::test_pending_historical_flow_resumes_instead_of_silently_switching_content` | старая публикация доигрывается по своему снапшоту |
| 60.2 | Политика миграции: continue / migrate compatible / re-evaluate changed | `partial` | `apps/api/app/content_publication.py:1` | `tests/test_course_content_connectivity.py::test_legacy_variables_completion_does_not_open_conditions_without_data_types` | только continue + явные replacements, re-evaluate нет |

## §61. Admin Panel

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 61.1 | Users и subscriptions | `partial` | `apps/api/app/accounts_api.py:321; apps/api/app/accounts_api.py:338` | `tests/test_account_services.py::test_admin_role_is_server_allowlisted_and_actions_are_audited` | есть метрики и revoke сессий, нет UI и управления подпиской |
| 61.2 | Courses, skills, lessons, exercises, knowledge chunks | `done` | `apps/api/app/admin_content_api.py:1; apps/web/app/admin/page.tsx:1` | `tests/test_admin_content.py::test_overview_matches_the_audit; tests/test_admin_content.py::test_lesson_detail_shows_checks_and_exercise` | admin API: обзор с проверкой полноты, список уроков с фильтрами, детали урока с проверками и заданием, список заданий; страница /admin. Редактирование остаётся в коде по ADR |
| 61.3 | Failed AI calls, flagged tutor, code-run failures, AI cost, feature flags, content versions | `partial` | `apps/api/app/accounts_api.py:321; apps/api/app/accounts_api.py:331` | `tests/test_account_services.py::test_admin_role_is_server_allowlisted_and_actions_are_audited` | есть статусы AI/runner и usage; flagged tutor, flags и версии контента нет |

## §62. Observability

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 62.1 | Structured logs и request ID | `done` | `apps/api/app/main.py:143` | `tests/test_observability_contracts.py::test_every_response_carries_a_correlation_id; tests/test_observability_contracts.py::test_the_log_line_repeats_the_id_and_never_the_payload` | id возвращается в заголовке, повторяется в JSON-строке лога, пароль и логин в лог не попадают |
| 62.2 | Error monitoring, tracing, DB latency, queue depth, sandbox latency | `partial` | `apps/api/app/accounts_api.py:321` | `нет` | есть счётчики статусов; трейсинга и метрик задержек нет |
| 62.3 | AI latency, token usage, cost per feature/user | `partial` | `apps/api/app/billing.py:63; apps/api/app/accounts_api.py:331` | `tests/test_account_services.py::test_billing_usage_counts_reserved_calls_without_assuming_free_provider` | токены и оценка стоимости есть, latency и per-feature cost нет |
| 62.4 | Не логировать пароли, токены, секреты и код | `done` | `apps/api/app/main.py:109; apps/api/app/ai_gateway.py:68` | `tests/test_knowledge_base.py::test_gateway_key_never_reaches_logs_or_responses` | в логах только тип ошибки и request id |

## §63. Backups

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 63.1 | Регулярные PostgreSQL backups, retention, отдельное storage | `partial` | `scripts/backup.sh:1` | `нет` | pg_dump, manifest, retention 7/4/6 реализованы; отдельного storage и расписания в compose нет |
| 63.2 | Object storage lifecycle и restore drill | `partial` | `scripts/restore-drill.sh:1; docs/backup.md:1` | `нет` | drill-скрипт есть, object storage отсутствует, теста нет |

## §64. Rate Limits и abuse

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 64.1 | Лимит login и регистрации | `done` | `apps/api/app/auth.py:36; apps/api/app/account_services.py:1` | `tests/test_account_services.py::test_auth_admission_is_durable_across_sessions_and_process_counter_clear` | durable fixed-window в БД |
| 64.2 | Лимит tutor messages и embeddings | `done` | `apps/api/app/mentor.py:246; apps/api/app/mentor.py:96` | `tests/test_mentor.py::test_ownership_and_rate_limit` | 5 вызовов в минуту на пользователя |
| 64.3 | Лимит code runs и размер очереди | `partial` | `apps/api/app/jobs_api.py:107` | `tests/test_practice.py::test_attempt_auth_csrf_and_owned_history` | 6/мин и 3 активных job; тест 429 отсутствует |
| 64.4 | Лимиты uploads, vacancy analysis, deep review, repository analysis | `partial` | `apps/api/app/http_limits.py:1; apps/api/app/vacancies.py:54` | `tests/test_completed_course.py::test_request_body_cap_and_error_response_redact_private_details` | есть cap тела и полей; rate limit вакансий и repo-анализа нет |
| 64.5 | Понятные пользователю лимиты вместо бесконечного unlimited | `partial` | `apps/api/app/billing.py:26` | `tests/test_account_services.py::test_billing_usage_counts_reserved_calls_without_assuming_free_provider` | показан дневной лимит AI-вызовов, credits и deep review нет |

## §65. Billing и тарифы

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 65.1 | Тарифы Free / Student / Pro / Advanced с разными entitlements | `partial` | `apps/api/app/billing.py:26` | `tests/test_account_services.py::test_billing_is_fail_closed_signed_idempotent_and_expiring` | только free (20) и pro (100) |
| 65.2 | Fail-closed checkout, подписанный webhook, идемпотентность и expiry | `done` | `apps/api/app/billing.py:100; apps/api/app/accounts_api.py:293` | `tests/test_account_services.py::test_billing_is_fail_closed_signed_idempotent_and_expiring` | без адаптера оплата недоступна, фейковых платежей нет |

## §66. Paywall

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 66.1 | Paywall не раньше aha moment; free проходит диагностику, gap, roadmap, первый урок, задачу и tutor | `partial` | `apps/api/app/billing.py:26; apps/api/app/learning_plan.py:204` | `tests/test_beginner_learning.py::test_novice_starts_with_explanation_without_diagnostic_or_fabricated_evidence` | paywall отсутствует, весь авторский курс открыт; gap по вакансии без UI |

## §67. Unit economics

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 67.1 | Unit economics: переменные (LLM, embeddings, execution, storage, fee), fixed и estimated cost на feature | `partial` | `apps/api/app/db/models.py:647; apps/api/app/accounts_api.py:331` | `tests/test_ai_admission.py::test_exact_money_requires_model_price_and_complete_integer_provider_usage` | учтены LLM и embeddings; execution, storage, fee и unit-cost отчёта нет |

## §68. Product Metrics

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 68.1 | North Star, acquisition, activation, engagement, retention, learning, revenue | `done` | `apps/api/app/analytics.py:1` | `tests/test_growth.py::test_funnel_is_computed_from_events; tests/test_growth.py::test_event_props_are_an_allow_list` | события продукта с закрытым списком полей; North Star, активация, вовлечённость, возврат и обучение считаются из событий; /admin/analytics |

## §69. Learning Metrics

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 69.1 | Pre-test/post-test, delayed test, transfer task | `partial` | `apps/api/app/assessment.py:152; apps/api/app/reviews_api.py:285` | `tests/test_reviews_api.py::test_today_contract_is_public_and_replays_without_duplicate_evidence` | есть diagnostic и delayed review; transfer task нет |
| 69.2 | Решение без подсказок и объяснение собственного решения | `partial` | `apps/api/app/skill_evidence.py:235; apps/api/app/reflections_api.py:53` | `tests/test_learning_integrity.py::test_written_practice_persists_once_without_mastery_credit` | independent считается, объяснение не оценивается |

## §70. Feedback loop

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 70.1 | Кнопки «помогло / не помогло» после AI-ответа и причины 👎 | `missing` | `нет` | `нет` | UI и API обратной связи отсутствуют |

## §71. Motivation и геймификация

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 71.1 | Streak, XP, уровни, achievements, milestones | `done` | `apps/api/app/gamification.py:1; apps/web/app/dashboard/progress-card.tsx:1` | `tests/test_gamification.py::test_api_returns_the_same_numbers_as_the_pricing_table; tests/test_gamification.py::test_achievements_are_predicates_over_facts; tests/test_gamification.py::test_streak_counts_days_with_a_completion` | XP по фиксированной таблице за проверенные действия, шесть уровней, серия по дням с завершённым уроком, шесть достижений-предикатов; карточка на дашборде

## §72. Difficulty Adaptation

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 72.1 | Повышать сложность после серии лёгких решений | `partial` | `apps/api/app/assessment.py:138` | `tests/test_assessment_bank.py::test_correct_answer_raises_the_next_difficulty` | работает только в диагностике, не в curriculum |
| 72.2 | При застревании проверять prerequisites и откатываться | `done` | `apps/api/app/prerequisites.py:1; apps/api/app/curriculum.py:115` | `tests/test_course_content_connectivity.py::test_active_lessons_resolve_to_an_acyclic_graph_with_closed_prerequisites` | заблокированные уроки не рекомендуются |

## §73. Frustration Detection

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 73.1 | Сигналы: failed runs, много подсказок, «не понимаю», reset; смена режима tutor | `done` | `apps/api/app/tutor_modes.py:96` | `tests/test_tutor_modes.py::test_failed_runs_switch_the_mode_without_asking; tests/test_tutor_modes.py::test_repeated_confusion_switches_to_explanation` | три проваленных запуска → debug_coach, два сигнала непонимания → teach; причина смены возвращается клиенту |

## §74. Confidence Calibration

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 74.1 | Вопрос «насколько уверен 1–5» и сравнение с результатом | `missing` | `нет` | `нет` | self-report уверенности не собирается |

## §75. User Explanation Tasks

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 75.1 | «Объясни, почему решение работает» и оценка понимания AI | `partial` | `apps/api/app/reflections_api.py:53` | `tests/test_learning_integrity.py::test_written_practice_persists_once_without_mastery_credit` | текст сохраняется как письменная практика, AI не оценивает |

## §76. Interview Mode

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 76.1 | HR simulation, technical questions, live coding, code reading, system discussion с адаптацией | `missing` | `нет` | `нет` | интервью-режима нет |

## §77. Weekly Report

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 77.1 | Недельный отчёт: сессии, упражнения, минуты, рост, повторяющаяся ошибка, цель; email/Telegram | `missing` | `нет` | `нет` | рассылки weekly report нет |

## §78. Notifications

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 78.1 | Конкретная ценность уведомления (забываемая тема, время повторения) | `partial` | `apps/api/app/notifications.py:110` | `tests/test_account_services.py::test_outbox_preferences_and_idempotency_prevent_unwanted_delivery` | текст общий, без темы и оценки времени |
| 78.2 | Частота — пользовательская настройка | `done` | `apps/api/app/accounts_api.py:198` | `tests/test_account_services.py::test_outbox_preferences_and_idempotency_prevent_unwanted_delivery` | email/telegram/review_reminders переключаются |

## §79. SEO и публичная часть

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 79.1 | Публичные страницы concepts, roadmaps, error explanations, interview guides, skill pages | `missing` | `apps/web/app/page.tsx:1` | `нет` | только лендинг |

## §80. Referral

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 80.1 | Пригласи друга → дни Pro или credits | `missing` | `нет` | `нет` | реферальной механики нет |

## §81. Localization

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 81.1 | Language-neutral Skill Graph | `done` | `apps/api/app/skill_graph.py:6` | `tests/test_skill_graph.py::test_authored_graph_has_valid_references_and_acyclic_prerequisites` | id и названия на английском, контент отдельно |
| 81.2 | concept_id + locale + content для ru/en | `missing` | `нет` | `нет` | locale-колонок и второго языка нет |

## §82. Accessibility

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 82.1 | Keyboard navigation, contrast, screen reader labels, font scaling, не только цвет, accessible editor | `partial` | `apps/web/app/learning/code-editor.tsx:1; apps/web/app/globals.css:1` | `нет` | есть aria-атрибуты и фокус-стили; аудита и тестов доступности нет |

## §83. Deployment MVP

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 83.1 | CDN/proxy, web, api, PostgreSQL, Redis, object storage, workers, AI gateway, Telegram, runner host | `partial` | `docker-compose.yml:1` | `нет` | есть db/api/web/dispatchers; Redis, object storage и runner host не в compose |
| 83.2 | Environments local / staging / production | `partial` | `.github/workflows/ci.yml:1` | `нет` | есть local и CI; staging/prod деплоя нет |

## §84. Архитектура V2: Repository Intelligence

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 84.1 | Repo ingestion → tree-sitter → symbols → graph → summaries → code index → review engine | `out-of-scope` | `нет` | `нет` | спец. §90: V2 repository intelligence вне Python MVP |

## §85. CI/CD

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 85.1 | lint → unit → integration → types → security → build → migration validation | `partial` | `.github/workflows/ci.yml:1` | `нет` | есть pytest, npm lint/build, alembic upgrade, browser smoke; dependency/security scanning нет |
| 85.2 | staging → smoke → production, тестирование prompt/model изменений | `partial` | `.github/workflows/ci.yml:47` | `нет` | staging/prod деплоя и eval-гейта нет |

## §86. Feature Flags

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 86.1 | Флаги github_import, large_repo_review, new_tutor_v2, new_mastery_model, new_vacancy_parser | `done` | `apps/api/app/feature_flags.py:1` | `tests/test_growth.py::test_rollout_is_stable_and_bounded; tests/test_growth.py::test_percentage_and_override` | пять флагов из спеки, детерминированная раскатка по хешу, исключение для пользователя важнее процента, запись в лог аудита |

## §87. Основные security threats

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 87.1 | Arbitrary code, бесконечные циклы, fork bombs, memory exhaustion, FS probing, network/metadata, mining | `done` | `apps/runner/runner_worker/policy.py:10; apps/runner/runner_worker/sandbox_landlock.py:1` | `tests/runner/tests/test_landlock_sandbox.py::LandlockSandboxTests::test_process_creation_and_exec_are_denied` | набор тестов на побег и лимиты |
| 87.2 | Malicious uploads, prompt injection, leaked secrets, dependency attacks | `partial` | `apps/api/app/http_limits.py:1; apps/api/app/knowledge_base.py:332` | `tests/test_knowledge_base.py::test_retrieved_text_is_labelled_untrusted_data_not_instructions` | есть cap тела и маркировка data; secret/dependency scanning нет |

## §88. Security checklist перед beta

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 88.1 | HTTPS, secrets вне repo, закрытая БД, сильный hashing, rate limits, sandbox, resource limits, network off | `partial` | `apps/api/app/auth.py:26; apps/api/app/security.py:18; apps/runner/runner_worker/policy.py:1` | `tests/runner/tests/test_landlock_sandbox.py::LandlockSandboxTests::test_network_access_is_denied` | код-часть есть; HTTPS, сеть и БД — задачи развёртывания |
| 88.2 | Upload limits, file type validation, secret scanning, dependency scanning | `partial` | `apps/api/app/http_limits.py:1` | `tests/test_completed_course.py::test_request_body_cap_and_error_response_redact_private_details` | есть только лимит тела; загрузок, secret и dependency scan нет |
| 88.3 | Backups, restore test, логи без секретов, удаление аккаунта, privacy policy | `partial` | `scripts/backup.sh:1; apps/api/app/account_services.py:1` | `tests/test_account_services.py::test_export_and_transactional_delete_include_derived_rows_and_preserve_other_user` | backup и удаление есть; restore drill не автоматизирован, privacy policy нет |

## §89. MVP Scope

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 89.1 | Пункты 1–13: регистрация, onboarding, цель, assessment, Skill Graph, mastery, roadmap, урок, quiz, редактор, sandbox, public/hidden tests, hint ladder | `partial` | `apps/api/app/main.py:51` | `tests/test_course_content_connectivity.py::test_each_active_lesson_has_exact_check_hint_ladder_and_published_version` | всё есть, кроме Monaco (ADR: CodeMirror); sandbox требует настройки host |
| 89.2 | Пункты 14–23: tutor, mistake memory, spaced review, dashboard, vacancy analyzer, billing, Telegram, accounting, admin, monitoring/backups | `partial` | `apps/api/app/mentor.py:186; apps/api/app/vacancies.py:143` | `tests/test_product_features.py::test_vacancy_history_gap_target_and_ownership` | ядро есть; dashboard без сессии, monitoring/backups частично, admin без UI |

## §90. Что НЕ входит в MVP

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 90.1 | C++ и ML/Data Science | `out-of-scope` | `нет` | `нет` | спец. §90 и UNIMPLEMENTED_STAGES: вне Python MVP |
| 90.2 | React live IDE и HTML/CSS preview | `out-of-scope` | `нет` | `нет` | спец. §90 |
| 90.3 | Native mobile, live collaboration, видео-платформа | `out-of-scope` | `нет` | `нет` | спец. §90 |
| 90.4 | Соцсеть, employer marketplace, сертификаты | `out-of-scope` | `нет` | `нет` | спец. §90 |
| 90.5 | Собственная LLM, Kubernetes, десятки микросервисов, полный large-repository engine | `out-of-scope` | `нет` | `нет` | спец. §90 и UNIMPLEMENTED_STAGES |

## §91–95. План, roadmap, beta-пользователи, гипотеза, moat

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 91–95.1 | 4-недельный план, 8–12-недельный roadmap, набор 20 beta-пользователей, гипотеза MVP и moat | `out-of-scope` | `нет` | `нет` | плановые и рыночные разделы не содержат требований к системе; граница зафиксирована §90 и UNIMPLEMENTED_STAGES |

## §96. Почему пользователь не уйдёт в обычный AI-чат

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 96.1 | Удерживает structured educational state: задачи, ошибки, misconceptions, проекты, навыки, вакансии, review, roadmap | `partial` | `apps/api/app/db/models.py:756; apps/api/app/db/models.py:388` | `tests/test_mistake_memory.py::test_distinct_mapped_mistakes_increment_but_reprocessing_is_idempotent` | навыки, ошибки, review и roadmap есть; проекты/вакансии не входят в единый профиль |

## §97. Основные риски и mitigation

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 97.1 | Mitigation рисков: RAG/tests/evals против ошибок AI, hint ladder против копирования, limits/caching против стоимости, изоляция sandbox, узкий scope, версионирование контента, daily plan и Telegram против оттока | `partial` | `apps/api/app/knowledge_base.py:232; apps/api/app/skill_evidence.py:235; apps/api/app/ai_admission.py:1` | `tests/test_ai_admission.py::test_hourly_limit_allows_six_calls_and_counts_failures_across_sessions` | RAG, tests, hint ladder, лимиты и изоляция есть; evals, routing и retention-механики частично |

## §98–99. Репозиторий и структура backend-модулей

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 98–99.1 | Монорепо /apps/web, /apps/api, /apps/telegram, /services/sandbox, /packages, /content, /evals, /infra; модули auth…notifications | `partial` | `apps/; apps/api/app/` | `нет` | есть apps/web, apps/api, apps/runner; telegram-сервиса, packages, content и evals-каталога нет; модули файлами |

## §100–101. Content structure и exercise definition

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 100–101.1 | skills.yaml, modules/lessons/exercises в git + importer; exercise: id, skills, starter_code, public_tests, rubric, hints | `partial` | `apps/api/app/learning_content.py:1; apps/api/app/runner_exercise_content.py:1` | `tests/test_completed_course.py::test_new_authored_examples_and_all_reference_solutions_match_cases` | контент в Python-модулях, не YAML; rubric в exercise definition нет |
| 100–101.2 | LLM может генерировать варианты задания, но solver/test pipeline проверяет до публикации | `partial` | `apps/api/app/ai_curriculum.py:237; apps/api/app/practice_catalog.py:1` | `tests/test_product_features.py::test_generated_bound_code_pins_authored_version_and_reuses_job` | AI выбирает только authored exercise из каталога, не генерирует grader |

## §102. API/Data flow Tutor Message

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 102.1 | receive → intent → active assessment/exercise → profile/skills/mistakes → knowledge → mode/model → generate → validate → store → memory → cost | `partial` | `apps/api/app/mentor.py:186` | `tests/test_mentor.py::test_success_records_usage_with_safe_token_types_and_character_counts` | нет intent detection, выбора mode/model и извлечения памяти из ответа |

## §103–106. Latency, error handling, autosave, работа без AI

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 103–106.1 | Latency targets и реальные стадии долгих процессов | `missing` | `нет` | `нет` | замеров latency и progress-стадий нет; deep review отсутствует |
| 103–106.2 | AI недоступен: retry/fallback, сообщение сохранено, понятная ошибка; sandbox недоступен: код сохранён, submission не теряется | `partial` | `apps/api/app/mentor.py:259; apps/api/app/practice.py:271` | `tests/test_mentor.py::test_failure_saved_and_explicit_retry` | сообщение и код сохраняются; retry/fallback автоматически не выполняются |
| 103–106.3 | Autosave и snapshots: debounce, server draft, local fallback, version, revert перед AI-refactor | `partial` | `apps/web/app/learning/coding-practice.tsx:171` | `нет` | только local fallback с версией; server draft, debounce и snapshots нет |
| 103–106.4 | Работа без AI: уроки, quiz, исполнение кода, тесты, dashboard, cached roadmap, история прогресса | `partial` | `apps/api/app/learning.py:459; apps/api/app/jobs_api.py:43` | `tests/test_beginner_learning.py::test_course_orientation_explains_actual_unconfigured_tutor` | уроки, quiz и план работают; исполнение кода зависит от настроенного runner |

## §107–109. Будущие пути, employer layer, монетизация

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 107–109.1 | Frontend/Data Analysis/ML/AI-LLM/C++ paths, employer layer, B2B-монетизация | `out-of-scope` | `нет` | `нет` | спец. §90 и UNIMPLEMENTED_STAGES: вне Python MVP |

## §110. Критические решения до кодинга

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 110.1 | Зафиксировать path, язык, провайдера, fallback, бюджет, изоляцию sandbox, формулу mastery, evidence, hint ladder, таксономию ошибок, память, privacy, лимиты, Telegram scope, non-goals | `partial` | `docs/decisions.md:1; docs/runner-security-review.md:1` | `нет` | большинство решений зафиксировано ADR; таксономии ошибок и формальных free/pro лимитов нет |

## §111. P0 / P1 / P2 / P3 backlog

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 111.1 | P0/P1 закрыты, P2/P3 — repository intelligence, interview mode, портфолио-страница и другие языки | `partial` | `docs/decisions.md:1; apps/api/app/projects.py:197` | `tests/test_product_features.py::test_projects_idempotency_validation_and_private_portfolio` | P0 закрыт почти полностью; P2/P3 вне scope, interview mode отсутствует |

## §112–115. Финальная формула, рекомендация, источники, следующие шаги

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| 112–115.1 | Архитектурная формула, коммерческая формулировка, список технических источников и порядок внедрения | `partial` | `docs/decisions.md:1; README.md:86` | `нет` | формула реализована; источники и порядок шагов — документация, не код |

## README: Learning Platform

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| README-1.1 | 90 учебных навыков и уроков; обучение от Python basics до backend; knowledge checks и quiz; практические задания; система подсказок; spaced repetition; персональный roadmap; прогресс и mastery | `partial` | `apps/api/app/learning_content.py:1; apps/api/app/learning_plan.py:64; apps/api/app/reviews.py:58` | `tests/test_completed_course.py::test_all_graph_skills_have_valid_lesson_and_trusted_practice` | всё перечисленное есть, кроме полного solution и «сегодняшней» сессии |

## README: AI Tutor

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| README-2.1 | AI-чат с учебным контекстом; локальный RAG по актуальной версии урока; разбор ошибок и пользовательского кода; AI-feedback письменных заданий; ограничение AI usage; учёт использования и стоимости | `partial` | `apps/api/app/mentor.py:186; apps/api/app/knowledge_base.py:232; apps/api/app/ai_admission.py:1` | `tests/test_knowledge_base.py::test_retrieved_version_matches_the_lesson_version_the_learner_sees` | чат, RAG, лимиты и учёт есть; код ученика в AI не отправляется и feedback по нему нет |

## README: Python Practice

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| README-3.1 | Контракт solve(payload); публичные примеры; скрытые тесты; сохранение решений; история попыток; асинхронная очередь; исполнение вне API отдельным Runner | `partial` | `apps/api/app/runner_exercise_content.py:1; apps/api/app/jobs_api.py:77; apps/api/app/practice.py:199` | `tests/test_completed_course.py::test_coding_specification_hides_keys_and_jobs_are_idempotent_without_runner` | всё есть; исполнение работает только после настройки Runner (fail-closed) |

## README: Authentication & Security

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| README-4.1 | Cookie-based sessions; Argon2; CSRF; подтверждение email; password reset; отзыв сессий; export; удаление аккаунта; audit административных операций | `done` | `apps/api/app/auth.py:42; apps/api/app/security.py:18; apps/api/app/accounts_api.py:79` | `tests/test_account_services.py::test_reset_changes_password_revokes_every_session_and_rejects_replay` | полный набор покрыт тестами account_services |

## README: Learning Model, Career, Projects

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| README-5.1 | Knowledge / Practice / Independence / Retention; анализ вакансии (требования, технологии, evidence, gaps, перестройка roadmap); проектные шаблоны, milestones, история артефактов, проверка комплектности, публикация в портфолио | `partial` | `apps/api/app/skill_evidence.py:38; apps/api/app/vacancies.py:143; apps/api/app/projects.py:129` | `tests/test_product_features.py::test_vacancy_history_gap_target_and_ownership` | четыре измерения и вакансии есть; портфолио без stack/tests, gap без UI |

## README: Architecture, Integrations, CI

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| README-6.1 | Модульный монолит; отдельные notification/execution dispatcher, Runner, email/Telegram/billing adapters; Docker Compose; GitHub Actions; Windows launchers | `partial` | `docker-compose.yml:1; .github/workflows/ci.yml:1; scripts/start-api.ps1:1` | `tests/test_platform_encoding.py::test_locale_independent_upgrade_rollback_preserves_data_and_registration` | compose, CI и Windows-скрипты есть; реальные адаптеры требуют credentials |

## UNIMPLEMENTED_STAGES: Требует настройки

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| UNIMPL-1.1 | AI Gateway и платные embeddings (endpoint/model/key/цены); email и платёжный провайдер; Telegram webhook и outbox dispatcher; Runner host (runsc/seccomp/AppArmor/userns/cgroups, сертификаты, attestation, reaper); ingress/TLS, secret mounts, monitoring, backup restore drill | `partial` | `apps/api/app/ai_gateway.py:39; apps/api/app/notifications.py:32; apps/runner/runner_worker/policy.py:70; docs/runner-deployment.md:1` | `tests/test_runner_client.py::test_missing_configuration_fails_closed_without_network` | код и контракты готовы, реальные ключи/провайдеры/host не настроены; исполнение fail-closed |

## UNIMPLEMENTED_STAGES: Осознанные границы (реализовано)

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| UNIMPL-2.1 | URL вакансии не фетчится, анализируется вставленный текст с точными фрагментами; milestone-артефакты проверяются на наличие разделов; свободные ответы рекомендательные, evidence создают только authored tests; mastery/retention — объяснимые эвристики | `done` | `apps/api/app/vacancies.py:43; apps/api/app/projects.py:178; apps/api/app/skill_evidence.py:285; apps/api/app/reviews.py:58` | `tests/test_product_features.py::test_vacancy_extraction_keeps_exact_evidence_and_negation` | границы зафиксированы кодом и проверяются тестами |

## UNIMPLEMENTED_STAGES: Осознанные границы (вне scope)

| № | Требование | Статус | Код | Тест | Комментарий |
|---|---|---|---|---|---|
| UNIMPL-3.1 | C++, ML, React live IDE, full repository execution, native apps, социальные функции, сертификаты и Kubernetes остаются вне Python MVP | `out-of-scope` | `нет` | `нет` | UNIMPLEMENTED_STAGES «Осознанные границы» + спец. §90 |

## Главные пробелы (missing)

| № | Пробел | Почему это важно |
|---|---|---|
| 1 | §49 Code review кода ученика | нет разбора пользовательского кода и обучающих вопросов вместо переписанного решения |
| 2 | §40 Rubric-оценка | оценка только pass/fail по тестам, rubric и веса отсутствуют |
| 3 | §41 AI-feedback по submission | mentor не получает код и результаты тестов, поэтому не объясняет ошибку |
| 4 | §24 AI Evaluation Framework | нет автоматического benchmark, rubric-прогонов и AI-метрик |
| 5 | §51 Secret Detection | нет поиска ключей, redaction и предупреждения о ротации |
| 6 | §86 Feature Flags | нет механизма поэтапного включения и быстрого выключения функций |
| 7 | §17 Interaction/Behavioral Memory | нет сводок сессий и поведенческих сигналов обучения |
| 8 | §76 Interview Mode | mock interview и адаптивные вопросы по вакансии не реализованы |
| 9 | §77 Weekly Report | нет недельного отчёта и его доставки в email/Telegram |
| 10 | §68 Product/learning metrics | нет событий и аналитики продукта, кроме usage AI и статусов job |

## Замечания по границам scope

- `out-of-scope` для C++, ML/Data Science, React live IDE, native apps, соцфункций, сертификатов, Kubernetes, микросервисов и large-repository engine опирается на §90 спецификации и раздел «Осознанные границы» в `UNIMPLEMENTED_STAGES.md`.
- Замена Monaco на CodeMirror 6, отказ от pgvector в пользу `LargeBinary`, отсутствие retries/fallback в AI Gateway и fail-closed Runner зафиксированы ADR в `docs/decisions.md`.
- Repository Intelligence (§42–48, §84) вынесен целиком: в коде нет ни таблиц `repository_*`, ни зависимости tree-sitter, ни загрузки архивов.
- Строки без теста сознательно оставлены `partial`, даже если поведение выглядит рабочим: это соответствует правилу «нет теста — не done».
