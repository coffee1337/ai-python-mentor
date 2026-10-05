from sqlalchemy import select

from app import ai_gateway, knowledge_base
from app.ai_embeddings import LOCAL_EMBEDDING_MODEL
from app.db.models import KnowledgeChunk
from app.db.session import get_db
from app.main import app
from test_auth import client
from test_learning import register, onboard
from test_mentor import provider, send


def test_first_chat_builds_local_index_and_releases_transaction_before_gateway(client, provider, monkeypatch):
    register(client)
    onboard(client)
    original_dependency = app.dependency_overrides[get_db]
    active = []

    def tracked_dependency():
        generator = original_dependency()
        db = next(generator)
        active.append(db)
        try:
            yield db
        finally:
            active.pop()
            generator.close()

    app.dependency_overrides[get_db] = tracked_dependency
    original_generate = ai_gateway.generate_with_usage

    def checked_generate(*args, **kwargs):
        assert active and not active[-1].in_transaction()
        return original_generate(*args, **kwargs)

    monkeypatch.setattr(ai_gateway, "generate_with_usage", checked_generate)
    try:
        assert send(client, message="Как присваивание связывает имя и значение?").status_code == 200
    finally:
        app.dependency_overrides[get_db] = original_dependency
    with next(original_dependency()) as db:
        rows = list(db.scalars(select(KnowledgeChunk)))
        assert rows
        assert {row.embedding_model for row in rows} == {LOCAL_EMBEDDING_MODEL}
        assert {row.skill_id for row in rows} == {"python.variables"}


def test_nested_references_use_existing_section_names_and_never_index_answer_keys():
    snapshot = {"exercise_id": "reference-v1", "lesson": {
        "checkpoint": {"prompt": "Explain the concept", "choices": ["secret choice"], "answer": "secret answer"},
        "misconception_check": {"misconception": "Possible mistake", "prompt": "Reflect on the mistake"},
        "question": "Graded question", "answer": "Final secret",
    }}
    pairs = knowledge_base.snapshot_texts(snapshot, "reference-v1")
    assert pairs == [("checkpoint", "Explain the concept"),
                     ("misconception_check", "Possible mistake"),
                     ("misconception_check", "Reflect on the mistake")]
    assert all(section in knowledge_base.INDEXABLE_SECTIONS for section, _ in pairs)
    assert "secret" not in " ".join(text for _, text in pairs)
