"""Export public SEO content from the authored course.

Public pages are built from a generated snapshot, not from a runtime API call: a
crawler must never need an account, and a search engine must see the same text the
learner does. Only published theory is exported — questions, choices and answers stay
out, exactly like the knowledge index.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.learning_content import LESSONS
from app.skill_graph import SKILLS

DESTINATION = ROOT / "apps" / "web" / "content" / "seo.json"
PHASES = [
    ("first-programs", "Первые программы", "Научиться читать код, хранить значения и выбирать действия по условиям."),
    ("python-basics", "Основа Python", "Повторения, функции, коллекции и ошибки — рабочий минимум языка."),
    ("python-backend", "Python Backend", "Запросы сайта, API, базы данных, проверки и устройство серверного приложения."),
]
SLUGS = {"python.core": "first-programs", "python.backend": "python-backend"}


def slug(lesson_id: str) -> str:
    return lesson_id.replace("-v1", "").replace("-v2", "").replace("_", "-")


def short(text: str, limit: int = 180) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def build() -> dict:
    skills = {skill["id"]: skill for skill in SKILLS}
    concepts = []
    for lesson in LESSONS:
        concepts.append(
            {
                "slug": slug(lesson["id"]),
                "title": lesson["title"],
                "skill_id": lesson["skill_id"],
                "skill": skills.get(lesson["skill_id"], {}).get("name", lesson["skill_id"]),
                "phase": SLUGS.get(skills.get(lesson["skill_id"], {}).get("category", ""), "python-basics"),
                "summary": short(lesson.get("why_it_matters") or lesson.get("goal") or lesson.get("body", "")),
                "body": lesson.get("body", ""),
                "minutes": lesson.get("minutes", 15),
                "difficulty": lesson.get("difficulty", "beginner"),
            }
        )
    skill_pages = []
    for skill in SKILLS:
        related = [item for item in concepts if item["skill_id"] == skill["id"]]
        skill_pages.append(
            {
                "id": skill["id"],
                "slug": skill["id"].replace(".", "-"),
                "name": skill["name"],
                "category": skill["category"],
                "description": skill["description"],
                "lessons": [{"slug": item["slug"], "title": item["title"]} for item in related],
            }
        )
    roadmaps = []
    for phase_id, title, outcome in PHASES:
        lessons = [item for item in concepts if item["phase"] == phase_id]
        roadmaps.append(
            {
                "slug": phase_id,
                "title": title,
                "outcome": outcome,
                "lessons": [{"slug": item["slug"], "title": item["title"], "minutes": item["minutes"]} for item in lessons],
                "minutes": sum(item["minutes"] for item in lessons),
            }
        )
    errors = []
    for lesson in LESSONS:
        check = lesson.get("misconception_check") or {}
        if isinstance(check, dict) and check.get("misconception"):
            errors.append(
                {
                    "slug": slug(lesson["id"]),
                    "title": short(check["misconception"], 90),
                    "lesson": lesson["title"],
                    "lesson_slug": slug(lesson["id"]),
                    "misconception": check["misconception"],
                    "correction": short(lesson.get("conclusion") or lesson.get("body", ""), 400),
                }
            )
    return {
        "generated_from": "authored course",
        "concepts": concepts,
        "skills": skill_pages,
        "roadmaps": roadmaps,
        "errors": errors,
    }


def main() -> int:
    payload = build()
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(
        f"seo: {len(payload['concepts'])} concepts, {len(payload['skills'])} skills, "
        f"{len(payload['roadmaps'])} roadmaps, {len(payload['errors'])} errors -> {DESTINATION}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
