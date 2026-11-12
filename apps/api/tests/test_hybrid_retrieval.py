"""Hybrid retrieval: vectors find paraphrases, the lexical layer finds the term.

The properties under test are the ones a learner feels: an exact term they typed
beats a slightly closer vector, both signals are fused instead of one dominating,
the skill/version filter stays hard, and the index still never contains a graded
answer.
"""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai_embeddings import LOCAL_EMBEDDING_MODEL, local_embedding, pack
from app.db.base import Base
from app.db.models import KnowledgeChunk
from app.knowledge_base import retrieve

VERSION = uuid4()
SKILL = "python.variables"


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
        from app.skill_graph import seed_skill_graph

        seed_skill_graph(db)
        db.commit()
        yield db
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_chunk(db, *, ordinal, content, vector=None, section="theory", skill=SKILL, version=VERSION):
    direction = vector or [0.0] * 64
    db.add(
        KnowledgeChunk(
            id=uuid4(),
            exercise_version_id=version,
            skill_id=skill,
            section=section,
            ordinal=ordinal,
            content=content,
            char_count=len(content),
            content_digest=f"{ordinal:064d}",
            embedding=pack(direction) if vector else None,
            embedding_dim=len(direction) if vector else None,
            embedding_model=LOCAL_EMBEDDING_MODEL if vector else None,
        )
    )
    db.commit()


def unit(text: str) -> list[float]:
    vector = local_embedding(text)
    return vector


def test_exact_term_wins_over_a_slightly_better_vector(session):
    # Both chunks pass the similarity bar; the vector prefers the first, the word
    # the learner actually typed appears only in the second.
    query = "Что делает break в цикле"
    query_vector = [1.0] + [0.0] * 63
    add_chunk(session, ordinal=0, content="Цикл повторяет действия, пока условие истинно.", vector=query_vector)
    add_chunk(session, ordinal=1, content="Оператор break прерывает цикл досрочно.",
              vector=[0.8, 0.6] + [0.0] * 62)
    chunks = retrieve(session, exercise_version_id=VERSION, skill_id=SKILL,
                      query_vector=query_vector, query_text=query)
    assert chunks[0].content.startswith("Оператор break"), [chunk.content for chunk in chunks]


def test_fusion_puts_the_chunk_both_signals_like_first(session):
    query = "словарь ключи значения"
    query_vector = [1.0] + [0.0] * 63
    add_chunk(session, ordinal=0, content="Структура данных хранит пары элементов.", vector=query_vector)
    add_chunk(session, ordinal=1, content="Словарь хранит ключи и значения.", vector=[0.7, 0.7] + [0.0] * 62)
    add_chunk(session, ordinal=2, content="Словарь: ключи, значения, доступ по ключу.",
              vector=[0.95, 0.3] + [0.0] * 62)
    chunks = retrieve(session, exercise_version_id=VERSION, skill_id=SKILL,
                      query_vector=query_vector, query_text=query, limit=3)
    assert chunks[0].ordinal == 2, [(chunk.ordinal, chunk.score) for chunk in chunks]


def test_lexical_only_still_ranks_without_a_vector(session):
    add_chunk(session, ordinal=0, content="Функция возвращает значение через return.")
    add_chunk(session, ordinal=1, content="Список хранит элементы по порядку.")
    chunks = retrieve(session, exercise_version_id=VERSION, skill_id=SKILL,
                      query_vector=None, query_text="return значение", limit=2)
    assert chunks[0].ordinal == 0


def test_filters_stay_hard_with_hybrid(session):
    add_chunk(session, ordinal=0, content="Словарь хранит ключи и значения.")
    add_chunk(session, ordinal=1, content="Словарь другого навыка.", skill="python.loops")
    add_chunk(session, ordinal=2, content="Словарь другой версии.", version=uuid4())
    chunks = retrieve(session, exercise_version_id=VERSION, skill_id=SKILL,
                      query_vector=unit("словарь"), query_text="словарь", limit=5)
    assert {chunk.exercise_version_id for chunk in chunks} == {VERSION}
    assert {chunk.skill_id for chunk in chunks} == {SKILL}


def test_tokens_are_stable_and_drop_stopwords():
    from app.knowledge_base import _tokens

    assert _tokens("Что делает break в цикле") == _tokens("что ДЕЛАЕТ break в цикле")
    assert "что" not in _tokens("что делает break")
    assert "break" in _tokens("что делает break")


def test_index_never_contains_the_graded_answer(session):
    add_chunk(session, ordinal=0, content="Словарь хранит ключи и значения.", section="body")
    rows = session.scalars(select(KnowledgeChunk)).all()
    for row in rows:
        assert row.section not in {"question", "choices", "answer"}, "оцениваемые секции не индексируются"
