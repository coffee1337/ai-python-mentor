"""Add frozen content coverage and exact authored wrong-choice signals.

Existing mappings and published snapshots are never changed. Downgrade keeps
catalog entries referenced by learner history so rollback cannot erase facts.
"""
import json
from pathlib import Path
from uuid import UUID, NAMESPACE_URL, uuid5
import sqlalchemy as sa
from alembic import op
revision='0036_content_completion'
down_revision='0035_execution_jobs'
branch_labels=None
depends_on=None


def seeds():
    return json.loads((Path(__file__).parents[1]/'data'/'0036_content_completion.json').read_text(encoding='utf-8'))


def tables():
    return (
        sa.table('misconceptions',sa.column('code',sa.String),sa.column('skill_id',sa.String)),
        sa.table('misconception_versions',sa.column('id',sa.Uuid),sa.column('misconception_code',sa.String),sa.column('version',sa.Integer),
                 *[sa.column(k,sa.Text) for k in ('error_text','typical_wrong_explanation','remediation_text','remediation_exercise_id')],sa.column('remediation_exercise_version',sa.Integer)),
        sa.table('misconception_mappings',sa.column('id',sa.Uuid),sa.column('source_type',sa.String),sa.column('exercise_id',sa.String),sa.column('exercise_version',sa.Integer),sa.column('question_id',sa.String),sa.column('wrong_choice',sa.Text),sa.column('misconception_code',sa.String),sa.column('misconception_version_id',sa.Uuid)),
        sa.table('lesson_skills',sa.column('id',sa.Uuid),sa.column('lesson_id',sa.String),sa.column('skill_id',sa.String)),
    )


def upgrade():
    bind=op.get_bind(); misconceptions,versions,mappings,links=tables()
    frozen=seeds()
    # A fresh database has only the historical skill catalog. Seed missing FK
    # parents from this revision's frozen asset, before links and misconceptions.
    skills=sa.table('skills',sa.column('id',sa.String),sa.column('name',sa.String),
        sa.column('category',sa.String),sa.column('difficulty',sa.Float),
        sa.column('importance',sa.Float),sa.column('tags',sa.JSON),sa.column('description',sa.Text))
    for row in frozen['skills']:
        if bind.scalar(sa.select(skills.c.id).where(skills.c.id==row['id'])) is None:
            bind.execute(skills.insert().values(**row))
    for lesson,skill in frozen['lesson_skills']:
        if bind.scalar(sa.select(links.c.id).where(links.c.lesson_id==lesson,links.c.skill_id==skill)) is None:
            bind.execute(links.insert().values(id=uuid5(NAMESPACE_URL,'mentor:0036:link:'+lesson),lesson_id=lesson,skill_id=skill))
    for row in frozen['mappings']:
        where=[mappings.c[k]==row[k] for k in ('source_type','exercise_id','exercise_version','question_id','wrong_choice')]
        if bind.scalar(sa.select(mappings.c.id).where(*where)) is not None: continue
        if bind.scalar(sa.select(misconceptions.c.code).where(misconceptions.c.code==row['code'])) is None:
            bind.execute(misconceptions.insert().values(code=row['code'],skill_id=row['skill_id']))
        vid=UUID(row['version_id'])
        if bind.scalar(sa.select(versions.c.id).where(versions.c.id==vid)) is None:
            bind.execute(versions.insert().values(id=vid,misconception_code=row['code'],version=1,
                **{k:row[k] for k in ('error_text','typical_wrong_explanation','remediation_text','remediation_exercise_id','remediation_exercise_version')}))
        bind.execute(mappings.insert().values(id=UUID(row['mapping_id']),misconception_code=row['code'],misconception_version_id=vid,
            **{k:row[k] for k in ('source_type','exercise_id','exercise_version','question_id','wrong_choice')}))


def downgrade():
    bind=op.get_bind(); misconceptions,versions,mappings,links=tables()
    # Shared skills stay: they may now have learner evidence or graph references,
    # and IDs alone cannot distinguish pre-existing rows from rows seeded here.
    # Only migration-owned UUIDs are removed. Existing links/mappings stay intact.
    occurrences=sa.table('mistake_occurrences',sa.column('misconception_version_id',sa.Uuid))
    user_mistakes=sa.table('user_mistakes',sa.column('misconception_code',sa.String))
    for row in seeds()['mappings']:
        vid=UUID(row['version_id'])
        used=bind.scalar(sa.select(sa.func.count()).select_from(occurrences).where(occurrences.c.misconception_version_id==vid))
        used+=bind.scalar(sa.select(sa.func.count()).select_from(user_mistakes).where(user_mistakes.c.misconception_code==row['code']))
        if used: continue
        bind.execute(mappings.delete().where(mappings.c.id==UUID(row['mapping_id'])))
        if bind.scalar(sa.select(sa.func.count()).select_from(mappings).where(mappings.c.misconception_version_id==vid)): continue
        bind.execute(versions.delete().where(versions.c.id==vid))
        if not bind.scalar(sa.select(sa.func.count()).select_from(versions).where(versions.c.misconception_code==row['code'])):
            bind.execute(misconceptions.delete().where(misconceptions.c.code==row['code']))
    for lesson,skill in seeds()['lesson_skills']:
        bind.execute(links.delete().where(links.c.id==uuid5(NAMESPACE_URL,'mentor:0036:link:'+lesson)))
