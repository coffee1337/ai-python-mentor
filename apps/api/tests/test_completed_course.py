import contextlib
from copy import deepcopy
import io
from sqlalchemy import select
from app.completion_content import TOPICS
from app.learning import LessonResponse
from app.learning_content import LESSONS
from app.runner_exercise_content import RUNNER_EXERCISES
from app.skill_graph import SKILLS
from app.db.models import SkillEvidence, User
from app.db.account_models import NotificationOutbox, TelegramBinding
from app.db.session import get_db
from app.main import app
from test_auth import client, csrf


def test_all_graph_skills_have_valid_lesson_and_trusted_practice():
    assert len(LESSONS)==90
    assert {l['skill_id'] for l in LESSONS}=={s['id'] for s in SKILLS}
    for lesson in LESSONS:
        LessonResponse.model_validate(lesson)
        exercise=RUNNER_EXERCISES[lesson['id']+'-code']
        assert exercise['skill_id']==lesson['skill_id']
        assert {c['visibility'] for c in exercise['cases']}=={'public','hidden'}
        assert [h[0] for h in exercise['hints']]==[1,2,3,4,5]


def test_new_authored_examples_and_all_reference_solutions_match_cases():
    # Execute only reviewed repository-owned references, never learner source.
    for row in TOPICS:
        output=io.StringIO()
        with contextlib.redirect_stdout(output):exec(row['example'],{})
        assert output.getvalue().strip()==row['output'],row['lesson_id']
    for exercise in RUNNER_EXERCISES.values():
        namespace={};exec(exercise['solution'],namespace)
        for case in exercise['cases']:
            assert namespace['solve'](*deepcopy(case['args']),**deepcopy(case['kwargs']))==case['expected'],exercise['exercise_id']


def register(c):
    assert c.post('/auth/register',json={'email':'completed@example.com','password':'safe-password'}).status_code==201
    assert c.post('/onboarding',headers={'X-CSRF-Token':csrf(c)},json={'experience_level':'beginner','target_role':'Python Backend','weekly_minutes':180}).status_code==200


def test_coding_specification_hides_keys_and_jobs_are_idempotent_without_runner(client):
    register(client)
    response=client.get('/learning/exercises/variables-v1/coding-specification')
    assert response.status_code==200
    assert 'solution' not in response.json() and 'hints' not in response.json()
    assert len(response.json()['public_examples'])==1
    endpoint='/learning/exercises/variables-v1-code/jobs'
    body={'source_code':'def solve(p): return p["start"]+p["increment"]','language':'python','mode':'function'}
    headers={'X-CSRF-Token':csrf(client),'Idempotency-Key':'test-code-once'}
    first=client.post(endpoint,headers=headers,json=body)
    assert first.status_code==202 and first.json()['status']=='unavailable'
    assert client.post(endpoint,headers=headers,json=body).json()==first.json()
    with next(app.dependency_overrides[get_db]()) as db:
        assert db.scalar(select(SkillEvidence)) is None
    hints=client.get('/learning/exercises/variables-v1-code/hints')
    assert hints.status_code==200 and hints.json()['revealed']==[]
    assert client.post('/learning/exercises/variables-v1-code/hints',headers={**headers,'Idempotency-Key':'coding-hint-once'},json={'level':1}).status_code==200


def test_telegram_questions_enqueue_once_without_sending_messages(client,monkeypatch):
    register(client);monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET','x'*32)
    with next(app.dependency_overrides[get_db]()) as db:
        user=db.scalar(select(User));db.add(TelegramBinding(user_id=user.id,chat_id='123'));db.commit()
    payload={'update_id':1,'message':{'chat':{'id':123,'type':'private'},'from':{'id':123},'text':'Как работает цикл for?'}}
    headers={'X-Telegram-Bot-Api-Secret-Token':'x'*32}
    assert client.post('/webhooks/telegram',headers=headers,json=payload).json()['status']=='queued'
    assert client.post('/webhooks/telegram',headers=headers,json=payload).json()['status']=='duplicate'
    with next(app.dependency_overrides[get_db]()) as db:
        rows=db.scalars(select(NotificationOutbox).where(NotificationOutbox.template=='telegram_tutor')).all()
        assert len(rows)==1 and rows[0].status=='pending'


def test_request_body_cap_and_error_response_redact_private_details(client,monkeypatch,caplog):
    response=client.post('/auth/register',content=b'x'*(128*1024+1),headers={'Content-Type':'application/json'})
    assert response.status_code==413
    def broken_db():
        raise RuntimeError('private-user-code-and-password')
        yield
    monkeypatch.setitem(app.dependency_overrides,get_db,broken_db)
    response=client.get('/me')
    assert response.status_code==500
    assert response.headers.get('X-Request-ID')
    assert 'private-user-code-and-password' not in response.text
    assert 'private-user-code-and-password' not in caplog.text
