"""Behaviour tests for the extended diagnostic bank and adaptive branch.

These assert what the learner can observe, not how the selector is written.
"""
import pytest
from sqlalchemy import select

from app.assessment import _next_target, _pick_question, _nearest_slot
from app.assessment_content import (
    DIFFICULTY_PRIOR,
    MAX_QUESTIONS,
    QUESTIONS,
    QUESTIONS_BY_ID,
    validate_bank,
)
from app.db.models import AssessmentResponse, AssessmentRun, UserSkill
from app.db.session import get_db
from app.learning_content import EXERCISE_HINT_LADDERS, LESSONS
from app.knowledge_check_content import CHECKS
from app.main import app
from app.skill_graph import SKILLS
from test_auth import client, csrf

CORE_SKILL_IDS = tuple(
    skill["id"] for skill in SKILLS if skill["category"] == "python.core"
)


def setup_user(test_client, email, level="beginner"):
    from app.auth import _attempts

    _attempts.clear()
    assert test_client.post(
        "/auth/register", json={"email": email, "password": "safe-password"}
    ).status_code == 201
    assert test_client.post(
        "/onboarding",
        headers={"X-CSRF-Token": csrf(test_client)},
        json={
            "experience_level": level,
            "target_role": "Python Backend",
            "weekly_minutes": 180,
        },
    ).status_code == 200


def test_bank_covers_every_core_skill_at_least_once():
    covered = {question["skill_id"] for question in QUESTIONS}
    assert set(CORE_SKILL_IDS).issubset(covered)
    # Two questions per skill: one anchor, one probe.
    counts = {skill_id: 0 for skill_id in CORE_SKILL_IDS}
    for question in QUESTIONS:
        counts[question["skill_id"]] += 1
    assert set(counts.values()) >= {2}
    assert len({question["id"] for question in QUESTIONS}) == len(QUESTIONS)
    assert all(question["id"].endswith("-v1") for question in QUESTIONS)


def test_every_bank_question_resolves_in_the_skill_graph():
    graph_ids = {skill["id"] for skill in SKILLS}
    categories = {skill["id"]: skill["category"] for skill in SKILLS}
    for question in QUESTIONS:
        assert question["skill_id"] in graph_ids
        assert categories[question["skill_id"]] == "python.core"
        assert question["answer"] in question["choices"]
        assert len(set(question["choices"])) == len(question["choices"])
        assert 0.1 <= question["difficulty"] <= 0.9


def test_bank_with_an_unknown_skill_is_rejected():
    orphaned = (*QUESTIONS, {"id": "orphan-v1", "skill_id": "python.ghost",
                              "difficulty": 0.5, "prompt": "p",
                              "choices": ["a", "b"], "answer": "a"})
    with pytest.raises(ValueError):
        validate_bank(orphaned)


def test_bank_missing_a_core_skill_is_rejected():
    thinned = tuple(
        question for question in QUESTIONS if question["skill_id"] != CORE_SKILL_IDS[-1]
    )
    with pytest.raises(ValueError):
        validate_bank(thinned)


def test_question_outside_its_skill_range_is_rejected():
    broken = tuple(
        {**question, "difficulty": 0.85} if question["id"] == "sets-membership-v1" else question
        for question in QUESTIONS
    )
    with pytest.raises(ValueError):
        validate_bank(broken)


def test_correct_answer_raises_the_next_difficulty():
    start = next(question for question in QUESTIONS if question["id"] == "variables-v1")
    higher = _next_target(start["difficulty"], correct=True)
    lower = _next_target(start["difficulty"], correct=False)
    assert higher > start["difficulty"]
    assert lower < start["difficulty"]


def test_branch_never_repeats_a_question_or_a_skill_back_to_back():
    asked = ["variables-v1"]
    current = QUESTIONS_BY_ID["variables-v1"]
    for _ in range(MAX_QUESTIONS - 1):
        nxt = _pick_question(
            set(asked),
            target_difficulty=_next_target(current["difficulty"], correct=True),
            exclude_skill_id=current["skill_id"],
        )
        assert nxt is not None
        assert nxt["id"] not in asked
        assert nxt["skill_id"] != current["skill_id"]
        asked.append(nxt["id"])
        current = nxt


def test_branch_ends_when_the_bank_is_exhausted():
    assert _pick_question({question["id"] for question in QUESTIONS},
                          target_difficulty=0.5) is None


def test_early_stop_respects_max_questions(client):
    setup_user(client, "bank-early-stop@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    state = client.get("/assessment").json()
    answered = 0
    while state["question"] is not None:
        assert state["question"]["total_questions"] == MAX_QUESTIONS
        question = state["question"]
        state = client.post(
            "/assessment/answers",
            headers=headers,
            json={"question_id": question["id"], "answer": question["choices"][0]},
        ).json()["state"]
        answered += 1
        assert answered <= MAX_QUESTIONS
    assert state["completed"] is True
    assert answered == MAX_QUESTIONS
    with next(app.dependency_overrides[get_db]()) as db:
        responses = db.scalars(select(AssessmentResponse)).all()
        assert len(responses) == MAX_QUESTIONS
        assert len({row.question_id for row in responses}) == MAX_QUESTIONS


def test_answer_never_reaches_the_client(client):
    setup_user(client, "bank-no-leak@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    first = client.get("/assessment")
    assert first.status_code == 200
    # "answer" as a key must not appear; "answered" is a public count.
    assert '"answer"' not in first.text
    question = first.json()["question"]
    assert set(question) == {
        "id", "skill_id", "difficulty", "prompt", "choices",
        "question_number", "total_questions",
    }
    answered = client.post(
        "/assessment/answers",
        headers=headers,
        json={"question_id": question["id"], "answer": question["choices"][0]},
    )
    assert answered.status_code == 200
    body = answered.json()
    assert '"answer"' not in answered.text
    assert set(body) == {"correct", "feedback", "state"}
    assert body["state"]["question"] is not None
    # The next question is public too, and still carries no answer key.
    assert set(body["state"]["question"]) == {
        "id", "skill_id", "difficulty", "prompt", "choices",
        "question_number", "total_questions",
    }


def test_weak_run_starts_at_the_beginning_and_never_fails_the_learner(client):
    setup_user(client, "bank-weak-start@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    first = client.get("/assessment").json()["question"]
    assert first["skill_id"] == "python.variables"
    state = None
    for _ in range(MAX_QUESTIONS):
        question = state["question"] if state else first
        # Always the first offered choice, which is right roughly half the time.
        state = client.post(
            "/assessment/answers",
            headers=headers,
            json={"question_id": question["id"], "answer": question["choices"][0]},
        ).json()["state"]
    assert state["completed"] is True
    assert 0.0 <= state["score"] <= 1.0
    assert "error" not in str(state).lower()
    # A weak run still produces a plan that starts at a prerequisite-ready root.
    plan = client.get("/learning/plan").json()
    assert plan["status"] == "ready"
    assert plan["recommended_lesson_id"] is not None
    assert client.get("/learning/path").json()["next_lesson_id"] is not None


def test_declaration_level_moves_the_starting_difficulty(client):
    setup_user(client, "bank-junior-start@example.com", level="junior")
    first = client.get("/assessment").json()["question"]
    prior = DIFFICULTY_PRIOR["junior"]
    assert abs(first["difficulty"] - prior) <= abs(
        min(abs(question["difficulty"] - prior) for question in QUESTIONS)
    )


def test_run_records_prior_for_every_asked_skill(client):
    setup_user(client, "bank-prior@example.com")
    headers = {"X-CSRF-Token": csrf(client)}
    state = client.get("/assessment").json()
    asked = []
    while state["question"] is not None:
        question = state["question"]
        asked.append((question["skill_id"], question["id"]))
        state = client.post(
            "/assessment/answers",
            headers=headers,
            json={"question_id": question["id"], "answer": question["choices"][0]},
        ).json()["state"]
    with next(app.dependency_overrides[get_db]()) as db:
        rows = db.scalars(select(UserSkill)).all()
        assert {row.skill_id for row in rows} == {skill_id for skill_id, _ in asked}
        assert all(row.evidence_count >= 1 for row in rows)


def test_each_lesson_has_a_check_and_a_hint_ladder():
    for lesson in LESSONS:
        lesson_id = lesson["id"]
        assert lesson_id in CHECKS, lesson_id
        assert lesson_id in EXERCISE_HINT_LADDERS, lesson_id
        ladder = EXERCISE_HINT_LADDERS[lesson_id]
        assert [level for level, _, _ in ladder["hints"]] == [1, 2, 3, 4, 5]
        assert [kind for _, kind, _ in ladder["hints"]] == [
            "direction", "concept", "step", "pseudocode", "solution",
        ]
        assert lesson["skill_id"] in {skill["id"] for skill in SKILLS}


def test_lesson_skill_and_prerequisites_resolve_without_cycles():
    graph_skills = {skill["id"] for skill in SKILLS}
    prerequisite_edges = {
        (edge[0], edge[1])
        for edge in __import__("app.skill_graph", fromlist=["EDGES"]).EDGES
        if edge[2] == "prerequisite"
    }
    roots = set()
    for lesson in LESSONS:
        # The two earliest authored lessons predate the prerequisites field.
        prerequisites = lesson.get("prerequisites", [])
        assert lesson["skill_id"] in graph_skills
        if not prerequisites:
            roots.add(lesson["skill_id"])
        for prerequisite in prerequisites:
            assert prerequisite in graph_skills
            assert (prerequisite, lesson["skill_id"]) in prerequisite_edges
    # Prerequisites resolve to earlier lessons, so the authored order is acyclic.
    position = {lesson["skill_id"]: index for index, lesson in enumerate(LESSONS)}
    for lesson in LESSONS:
        for prerequisite in lesson.get("prerequisites", []):
            assert position[prerequisite] < position[lesson["skill_id"]]
