"""Resume an owned pending historical publication without rewriting it."""
from sqlalchemy import select
from app.content_publication import PUBLICATION_REPLACEMENTS
from app.db.models import KnowledgeCheckSession, LessonCompletion, LessonSession


def resumable_publication(db, user_id):
    completed = set(db.scalars(select(LessonCompletion.lesson_id).where(LessonCompletion.user_id == user_id)))
    pending = []
    for model in (LessonSession, KnowledgeCheckSession):
        pending.extend(db.scalars(select(model).where(
            model.user_id == user_id, model.consumed_at.is_(None),
            model.lesson_id.in_(PUBLICATION_REPLACEMENTS),
        )))
    pending = [row for row in pending if row.lesson_id not in completed
               and PUBLICATION_REPLACEMENTS[row.lesson_id] not in completed]
    if not pending:
        return None
    row = max(pending, key=lambda item: item.created_at)
    return row.lesson_id, row.exercise_version_id
