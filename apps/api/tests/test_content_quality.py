"""Content quality gate: no placeholders, no untranslated stubs, complete lessons.

The course is the product. A lesson with an empty body, an "answer" that is not
among the choices, or an English placeholder inside Russian prose is a defect
that no unit test would otherwise catch.
"""
import re

import pytest

from app.learning_content import LESSONS
from app.runner_exercise_content import RUNNER_EXERCISES

FORBIDDEN = re.compile(r"\b(TODO|FIXME|TBD|Lorem|ipsum|placeholder|заглушк|xxx+)\b", re.IGNORECASE)
CYRILLIC = re.compile(r"[а-яА-ЯёЁ]")
LATIN_WORD = re.compile(r"[A-Za-z]{4,}")


def russian_share(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    return sum(bool(CYRILLIC.match(char)) for char in letters) / len(letters)


def test_every_lesson_is_structurally_complete():
    problems = []
    for lesson in LESSONS:
        for field in ("id", "title", "skill_id", "body", "example", "question", "answer"):
            value = lesson.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{lesson.get('id')}: empty {field}")
        if len(lesson.get("choices") or ()) < 3:
            problems.append(f"{lesson.get('id')}: fewer than three choices")
        if lesson.get("answer") not in (lesson.get("choices") or ()):
            problems.append(f"{lesson.get('id')}: answer is not one of the choices")
        if len(set(lesson.get("choices") or ())) != len(lesson.get("choices") or ()):
            problems.append(f"{lesson.get('id')}: duplicate choices")
    assert problems == [], "\n".join(problems[:20])


def test_no_placeholders_or_stub_text():
    problems = []
    for lesson in LESSONS:
        for field in ("title", "body", "example", "question", "answer"):
            value = lesson.get(field) or ""
            if FORBIDDEN.search(value):
                problems.append(f"{lesson['id']}.{field}: {FORBIDDEN.search(value).group(0)}")
        for choice in lesson.get("choices") or ():
            if FORBIDDEN.search(choice):
                problems.append(f"{lesson['id']}.choices: {FORBIDDEN.search(choice).group(0)}")
    assert problems == [], "\n".join(problems[:20])


def test_russian_prose_is_actually_russian():
    # Questions legitimately quote code, so the bar is "contains a Russian
    # sentence", not "half of the letters are Cyrillic".
    problems = []
    for lesson in LESSONS:
        for field in ("title", "body"):
            value = lesson.get(field) or ""
            share = russian_share(value)
            if share < 0.5:
                problems.append(f"{lesson['id']}.{field}: only {share:.0%} Cyrillic")
        question = lesson.get("question") or ""
        if russian_share(question) < 0.15 and not re.search(r"\b(Что|Как|Почему|Какой|Какая|Зачем)\b", question):
            problems.append(f"{lesson['id']}.question: no Russian sentence")
    assert problems == [], "\n".join(problems[:20])


def test_bodies_are_substantive():
    short = [(lesson["id"], len(lesson.get("body") or "")) for lesson in LESSONS
             if len(lesson.get("body") or "") < 200]
    assert short == [], f"lessons with a body shorter than 200 characters: {short[:10]}"


def test_examples_look_like_runnable_python():
    problems = []
    for lesson in LESSONS:
        example = lesson.get("example") or ""
        if "print" not in example and "def " not in example and "=" not in example:
            problems.append(lesson["id"])
    assert problems == [], f"examples without visible code: {problems[:10]}"


def test_every_coding_exercise_belongs_to_a_published_lesson():
    from app.content_publication import PUBLICATION_REPLACEMENTS

    lesson_ids = {lesson["id"] for lesson in LESSONS}
    allowed = lesson_ids | set(PUBLICATION_REPLACEMENTS) | set(PUBLICATION_REPLACEMENTS.values())
    orphans = sorted(row["lesson_id"] for row in RUNNER_EXERCISES.values()
                     if row["lesson_id"] not in allowed)
    assert orphans == [], f"coding exercises without a lesson: {orphans[:10]}"


def test_reading_only_lessons_do_not_demand_a_coding_solution():
    # Early lessons are authored as guided reading: asking for solve(payload)
    # before the learner has met functions would teach nothing.
    covered = {row["lesson_id"] for row in RUNNER_EXERCISES.values()}
    problems = sorted(lesson["id"] for lesson in LESSONS
                      if lesson.get("practice_submission_type") == "guided_reading"
                      and lesson["id"] in covered)
    assert problems == [], f"reading-only lessons with a coding exercise: {problems[:10]}"


def test_every_coding_exercise_has_a_solution_and_cases():
    problems = []
    for exercise_id, row in RUNNER_EXERCISES.items():
        if not (row.get("solution") or "").strip():
            problems.append(f"{exercise_id}: no solution")
        if len(row.get("cases") or ()) < 2:
            problems.append(f"{exercise_id}: fewer than two cases")
        if not any(case["visibility"] == "public" for case in row.get("cases") or ()):
            problems.append(f"{exercise_id}: no public case")
        if not any(case["visibility"] == "hidden" for case in row.get("cases") or ()):
            problems.append(f"{exercise_id}: no hidden case")
        prompt = row.get("prompt") or ""
        if FORBIDDEN.search(prompt) or russian_share(prompt) < 0.3:
            problems.append(f"{exercise_id}: prompt is a stub or not Russian")
    assert problems == [], "\n".join(problems[:20])


def test_lesson_ids_and_titles_are_unique():
    ids = [lesson["id"] for lesson in LESSONS]
    titles = [lesson["title"] for lesson in LESSONS]
    assert len(ids) == len(set(ids))
    assert len(titles) == len(set(titles))
    assert len(LESSONS) == 90
