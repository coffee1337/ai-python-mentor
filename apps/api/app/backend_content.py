"""Authored content for the `python.backend` track, wave one (phase 1).

Phase 1 covers the first nine skills of the authored backend prerequisite
chain.  The chain in `app.skill_graph.EDGES` is a single path, so a phase is
defined as a contiguous slice of that path: a lesson may only require the
skills that precede it, otherwise the phase boundary would promise material
the learner cannot reach yet.

Every practice task in this module is reading, prediction, or error-hunting
in foreign code.  The runner is fail-closed, so no lesson may promise that
learner code is executed.
"""

from __future__ import annotations

from typing import Final


BACKEND_PHASES: Final[tuple[dict, ...]] = (
    {
        "id": 1,
        "title": "HTTP и API",
        "summary": "Приложение принимает запрос, разбирает его и отдаёт предсказуемый ответ.",
        "skill_ids": (
            "backend.http_basics",
            "backend.rest",
            "backend.api_design",
            "backend.json",
            "backend.fastapi_basics",
            "backend.fastapi_routing",
            "backend.fastapi_dependencies",
            "backend.request_validation",
            "backend.response_models",
        ),
    },
    {
        "id": 2,
        "title": "Надёжность API",
        "summary": "Доступ, сессии, конфигурация, ошибки и фоновые задачи.",
        "skill_ids": (
            "backend.authentication",
            "backend.authorization",
            "backend.sessions",
            "backend.csrf",
            "backend.password_hashing",
            "backend.async_python",
            "backend.async_io",
            "backend.background_tasks",
            "backend.logging",
            "backend.configuration",
            "backend.environment_variables",
            "backend.error_handling",
            "backend.middleware",
            "backend.openapi",
            "backend.websockets",
        ),
    },
    {
        "id": 3,
        "title": "Данные и эксплуатация",
        "summary": "SQL и ORM, затем Redis, контейнеры, Git, CI, логи и наблюдаемость.",
        "skill_ids": (
            "backend.sql_basics",
            "backend.postgresql",
            "backend.sql_select",
            "backend.sql_joins",
            "backend.sql_indexes",
            "backend.transactions",
            "backend.isolation",
            "backend.migrations",
            "backend.sqlalchemy_core",
            "backend.sqlalchemy_orm",
            "backend.relationships",
            "backend.n_plus_one",
            "backend.connection_pooling",
            "backend.caching",
            "backend.redis_basics",
            "backend.docker_basics",
            "backend.linux_cli",
            "backend.git_basics",
            "backend.git_branching",
            "backend.ci_basics",
            "backend.ci_testing",
            "backend.structured_logging",
            "backend.observability",
            "backend.security_basics",
        ),
    },
)


def _body(
    *,
    goal: str,
    prerequisites: tuple[str, ...],
    theory: str,
    example_output: str,
    checkpoint_prompt: str,
    misconception: str,
    misconception_prompt: str,
    practice: str,
    conclusion: str,
) -> str:
    """Compose the reader-facing lesson text from the structured fields."""
    prereq_line = (
        "Перед началом: "
        + ", ".join(f"`{item}`" for item in prerequisites)
        + "."
        if prerequisites
        else "Перед началом: базовый синтаксис Python."
    )
    return (
        f"Цель: {goal}\n"
        f"{prereq_line}\n\n"
        f"Теория: {theory}\n\n"
        "Пример и ожидаемый вывод:\n"
        f"{example_output}\n\n"
        f"Checkpoint: {checkpoint_prompt}\n\n"
        f"Проверь заблуждение: {misconception} {misconception_prompt}\n\n"
        f"Практика: {practice}\n\n"
        f"Вывод: {conclusion}"
    )


def _lesson(
    *,
    lesson_id: str,
    title: str,
    skill_id: str,
    prerequisites: tuple[str, ...],
    difficulty: int,
    minutes: int,
    goal: str,
    theory: str,
    example: str,
    example_output: str,
    checkpoint_prompt: str,
    checkpoint_choices: tuple[str, ...],
    misconception: str,
    misconception_prompt: str,
    practice: str,
    conclusion: str,
    question: str,
    choices: tuple[str, ...],
    answer: str,
) -> dict:
    if answer not in choices:
        raise ValueError(f"{lesson_id}: the answer must be one of the choices")
    return {
        "id": lesson_id,
        "title": title,
        "skill_id": skill_id,
        "prerequisites": list(prerequisites),
        "phase": 1,
        "difficulty": difficulty,
        "minutes": minutes,
        "goal": goal,
        "theory": theory,
        "body": _body(
            goal=goal,
            prerequisites=prerequisites,
            theory=theory,
            example_output=example_output,
            checkpoint_prompt=checkpoint_prompt,
            misconception=misconception,
            misconception_prompt=misconception_prompt,
            practice=practice,
            conclusion=conclusion,
        ),
        "example": example,
        "example_output": example_output,
        "checkpoint": {
            "prompt": checkpoint_prompt,
            "choices": list(checkpoint_choices),
        },
        "misconception_check": {
            "misconception": misconception,
            "prompt": misconception_prompt,
        },
        "practice": practice,
        "conclusion": conclusion,
        "question": question,
        "choices": list(choices),
        "answer": answer,
    }


_HTTP_BASICS_EXAMPLE = '''from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import urllib.request


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"status": "ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


server = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.handle_request, daemon=True).start()
with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/health") as response:
    print(response.status)
    print(response.headers["Content-Type"])
    print(response.read().decode())'''

_HTTP_BASICS_OUTPUT = """200
application/json
{"status": "ok"}"""

_REST_EXAMPLE = '''routes = {
    ("GET", "/orders"): (200, [{"id": 1}]),
    ("POST", "/orders"): (201, {"id": 2}),
}


def handle(method, path):
    if (method, path) not in routes:
        return 404, {"error": "not_found"}
    return routes[(method, path)]


print(handle("GET", "/orders"))
print(handle("POST", "/orders"))
print(handle("DELETE", "/orders"))'''

_REST_OUTPUT = """(200, [{'id': 1}])
(201, {'id': 2})
(404, {'error': 'not_found'})"""

_API_DESIGN_EXAMPLE = '''contract = {
    "GET /orders": "200 + список заказов",
    "POST /orders": "201 + Location: /orders/2",
}


def check(rule):
    method, path = rule.split(" ")
    return {
        "method": method,
        "path": path,
        "has_status": any(part[:3].isdigit() for part in contract[rule].split()),
        "noun_in_path": path.strip("/").split("/")[-1].isidentifier(),
    }


for rule in contract:
    print(check(rule))'''

_API_DESIGN_OUTPUT = """{'method': 'GET', 'path': '/orders', 'has_status': True, 'noun_in_path': True}
{'method': 'POST', 'path': '/orders', 'has_status': True, 'noun_in_path': True}"""

_JSON_EXAMPLE = '''import json

payload = {"id": 7, "tags": ["python", "backend"], "owner": None}
encoded = json.dumps(payload, ensure_ascii=False)
print(encoded)
print(json.loads(encoded) == payload)
print(json.loads("[1, 2]") + [3])'''

_JSON_OUTPUT = """{"id": 7, "tags": ["python", "backend"], "owner": null}
True
[1, 2, 3]"""

_FASTAPI_BASICS_EXAMPLE = '''from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


client = TestClient(app)
response = client.get("/health")
print(response.status_code)
print(response.json())'''

_FASTAPI_BASICS_OUTPUT = """200
{'status': 'ok'}"""

_FASTAPI_ROUTING_EXAMPLE = '''from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

app = FastAPI()
orders = {"1": {"id": 1, "total": 500}}


@app.get("/orders/{order_id}")
def read_order(order_id: str) -> dict:
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="order not found")
    return orders[order_id]


client = TestClient(app)
print(client.get("/orders/1").json())
print(client.get("/orders/9").status_code)'''

_FASTAPI_ROUTING_OUTPUT = """{'id': 1, 'total': 500}
404"""

_FASTAPI_DEPENDENCIES_EXAMPLE = '''from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

app = FastAPI()


def current_tenant() -> str:
    return "tenant-42"


@app.get("/reports")
def reports(tenant: str = Depends(current_tenant)) -> dict:
    return {"tenant": tenant}


client = TestClient(app)
print(client.get("/reports").json())
app.dependency_overrides[current_tenant] = lambda: "tenant-test"
print(client.get("/reports").json())
app.dependency_overrides.clear()'''

_FASTAPI_DEPENDENCIES_OUTPUT = """{'tenant': 'tenant-42'}
{'tenant': 'tenant-test'}"""

_REQUEST_VALIDATION_EXAMPLE = '''from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI()


class OrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=32)
    quantity: int = Field(ge=1, le=100)


@app.post("/orders")
def create_order(payload: OrderIn) -> dict:
    return {"email": payload.email, "quantity": payload.quantity}


client = TestClient(app)
print(client.post("/orders", json={"email": "a@b.c", "quantity": 2}).status_code)
print(client.post("/orders", json={"email": "a@b.c", "quantity": 0}).status_code)
print(client.post("/orders", json={"email": "a@b.c", "quantity": 1, "extra": 1}).status_code)'''

_REQUEST_VALIDATION_OUTPUT = """200
422
422"""

_RESPONSE_MODELS_EXAMPLE = '''from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

app = FastAPI()


class UserOut(BaseModel):
    id: int
    email: str


class UserRow(BaseModel):
    id: int
    email: str
    password_hash: str


row = UserRow(id=1, email="a@b.c", password_hash="pbkdf2:sha256:1")


@app.get("/users/{user_id}", response_model=UserOut)
def read_user(user_id: int) -> UserRow:
    return row


print(TestClient(app).get("/users/1").json())'''

_RESPONSE_MODELS_OUTPUT = """{'id': 1, 'email': 'a@b.c'}"""


BACKEND_PHASE_ONE_LESSONS: Final[tuple[dict, ...]] = (
    _lesson(
        lesson_id="http-basics-v1",
        title="HTTP: запрос, статус и заголовки",
        skill_id="backend.http_basics",
        prerequisites=("python.functions",),
        difficulty=3,
        minutes=20,
        goal="Различать метод, путь, заголовки и код ответа HTTP и объяснять, зачем сервер объявляет длину тела ответа.",
        theory=(
            "HTTP — текстовый протокол поверх транспорта: клиент пишет строку запроса с методом и путём, "
            "затем заголовки и, при необходимости, тело. Сервер отвечает строкой состояния с кодом, "
            "своими заголовками и телом. Код ответа читают по первой цифре: 2xx означает, что запрос "
            "выполнен, 4xx — что запрос разбирать нельзя или нельзя выполнять, 5xx — что сбой произошёл "
            "на сервере. Заголовок Content-Type сообщает формат тела, а Content-Length — сколько байт "
            "в теле придёт; без него клиент не знает, где заканчивается ответ, и читает его по соединению."
        ),
        example=_HTTP_BASICS_EXAMPLE,
        example_output=_HTTP_BASICS_OUTPUT,
        checkpoint_prompt="Зачем сервер отправляет заголовок Content-Length вместе с телом ответа?",
        checkpoint_choices=(
            "Чтобы клиент знал, сколько байт читать из тела ответа",
            "Чтобы клиент понял, с какого адреса пришёл ответ",
            "Чтобы соединение не закрывалось до конца тела",
        ),
        misconception="Content-Type и Content-Length — одно и то же: оба описывают тело ответа.",
        misconception_prompt=(
            "Раздели их роли на примере ответа с JSON-телом: что сообщает каждая пара заголовков "
            "и что произойдёт, если длину объявить неверно?"
        ),
        practice=(
            "Дан серверный обработчик, который пишет в тело 20 байт, но объявляет Content-Length: 8. "
            "Объясни по шагам, что увидит клиент при чтении ответа, и предложи, где именно ошибка. "
            "Затем разберись с запросом, у которого заголовок Content-Type объявлен, а тела нет: "
            "какой код ответа уместнее и почему. Пиши объяснение, а не готовый код исправления."
        ),
        conclusion=(
            "Код ответа задаёт класс результата, Content-Type — формат тела, а Content-Length — его длину; "
            "все три читаются в ответе независимо друг от друга."
        ),
        question="Что сообщает клиенту заголовок Content-Length в ответе сервера?",
        choices=(
            "Размер тела ответа в байтах",
            "Время, которое сервер потратил на обработку",
            "Адрес, с которого пришёл ответ",
        ),
        answer="Размер тела ответа в байтах",
    ),
    _lesson(
        lesson_id="rest-api-v1",
        title="REST: ресурсы, методы и коды ответа",
        skill_id="backend.rest",
        prerequisites=("backend.http_basics",),
        difficulty=3,
        minutes=22,
        goal="Отличать ресурс от действия и выбирать метод и код ответа, которые описывают операцию без побочных эффектов.",
        theory=(
            "REST описывает предметную область как набор ресурсов, а каждый ресурс адресуется путём. "
            "GET читает ресурс и не должен менять состояние сервера, POST создаёт новый ресурс и потому "
            "не идемпотентен, а PUT и DELETE повторяемы: повторный вызов с тем же содержимым не меняет "
            "итог. Идемпотентность — это свойство метода, а не дисциплина разработчика. "
            "Правило именования: в пути находится имя ресурса во множественном числе, а действие передаётся "
            "методом; когда действие не сводится к CRUD, выносят отдельный ресурс, например "
            "`/orders/1/cancellation`. Коды ответа выбирают по смыслу: 200 с телом, 201 с заголовком "
            "Location для созданного ресурса, 204 без тела для успешного удаления, 404 для неизвестного "
            "ресурса."
        ),
        example=_REST_EXAMPLE,
        example_output=_REST_OUTPUT,
        checkpoint_prompt="Какой код ответа уместнее для успешного удаления ресурса без тела?",
        checkpoint_choices=(
            "204 без тела ответа",
            "200 с пустым телом ответа",
            "404, если клиент повторит запрос",
        ),
        misconception="POST идемпотентен, потому что клиент отправляет одно и то же тело запроса.",
        misconception_prompt=(
            "Объясни разницу: почему повторный PUT с тем же телом не создаёт вторую запись, "
            "а повторный POST создаёт, и какой код ответа сервер отдаёт в каждом случае."
        ),
        practice=(
            "Дан список маршрутов: `POST /createUser`, `GET /orders/1/delete`, `DELETE /orders/1`, "
            "`PUT /orders/1`. Найди два маршрута, название которых нарушает правило «действие передаётся "
            "методом», и объясни, как их переименовать без изменения поведения. Отдельно реши, "
            "какой код ответа должен вернуть сервер для DELETE и почему тело здесь не нужно."
        ),
        conclusion=(
            "Путь адресует ресурс, метод задаёт операцию и её идемпотентность, а код ответа сообщает "
            "результат операции по смыслу, а не по привычке."
        ),
        question="Какое свойство делает DELETE безопасным для повторного вызова сети?",
        choices=(
            "Идемпотентность: удаление уже отсутствующего ресурса не меняет итог",
            "Отсутствие тела запроса",
            "То, что метод всегда возвращает код 204",
        ),
        answer="Идемпотентность: удаление уже отсутствующего ресурса не меняет итог",
    ),
    _lesson(
        lesson_id="api-design-v1",
        title="Проектирование API: контракт до кода",
        skill_id="backend.api_design",
        prerequisites=("backend.rest",),
        difficulty=4,
        minutes=24,
        goal="Описать контракт эндпоинта до реализации и найти в нём места, где клиент не сможет догадаться о результате.",
        theory=(
            "Контракт — это обещание, которое сервер даёт клиенту: путь, метод, набор полей, коды ответа "
            "и форма ошибки. Контракт пишется до кода, потому что иначе форма ответа вырастает из того, "
            "что случайно вернул обработчик. Устойчивая форма ошибки — одна на всё API: клиенту нужен "
            "стабильный код, а не текст исключения. Изменение смысла поля требует новой версии контракта, "
            "иначе расходится накопленная статистика ошибок у клиентов. Пагинация и сортировка задаются "
            "параметрами запроса, а не догадками клиента; формат даты — единый для всех полей, "
            "иначе клиенту приходится угадывать часовой пояс."
        ),
        example=_API_DESIGN_EXAMPLE,
        example_output=_API_DESIGN_OUTPUT,
        checkpoint_prompt="Что должно произойти с контрактом, если клиент начинает читать поле как дату, а сервер отдаёт его строкой?",
        checkpoint_choices=(
            "Контракт нужно изменить так, чтобы форма поля была зафиксирована явно",
            "Ничего: строковое поле можно читать как дату в любом случае",
            "Нужно удалить поле из ответа",
        ),
        misconception="Форма ответа может уточняться по ходу разработки, пока клиент не задал вопрос об этом поле.",
        misconception_prompt=(
            "Приведи два случая, когда правка формы ответа ломает уже написанный клиент, "
            "и объясни, почему версионирование контракта дешевле такой правки."
        ),
        practice=(
            "Дан черновик контракта из трёх правил: `GET /orders` без кодов ошибок, "
            "`POST /orders` с полями `user` и `items` без указания обязательности, "
            "`GET /orders/{id}` с датой в формате `MM/DD/YYYY`. Найди три дыры, которые оставят "
            "клиента без догадки, и опиши для каждой, чего не хватает в контракте. Не пиши код "
            "реализации и не подставляй готовые ответы вместо рассуждения."
        ),
        conclusion=(
            "Контракт фиксирует путь, метод, поля, коды и форму ошибки раньше реализации, и любое "
            "изменение смысла требует новой версии, а не правки на месте."
        ),
        question="Почему форму ошибки фиксируют в контракте до реализации?",
        choices=(
            "Чтобы клиент опирался на стабильный код, а не на текст исключения",
            "Чтобы сервер не тратил время на логирование",
            "Чтобы ошибки не попадали в ответ вовсе",
        ),
        answer="Чтобы клиент опирался на стабильный код, а не на текст исключения",
    ),
    _lesson(
        lesson_id="json-handling-v1",
        title="JSON: сериализация данных обмена",
        skill_id="backend.json",
        prerequisites=("backend.api_design",),
        difficulty=3,
        minutes=20,
        goal="Сериализовать словарь в JSON, читать его обратно и предсказывать, как значения Python выглядят в JSON.",
        theory=(
            "JSON — текстовый формат обмена, в котором есть только объект, массив, строка, число, "
            "true, false и null. Модуль json переводит словарь в строку функцией dumps, а строку обратно "
            "в структуру функцией loads. Значение None превращается в null, а не в строку \"None\", "
            "поэтому клиент на другом языке не споткнётся о неожиданный тип. Ключи словаря сериализуются "
            "в строки всегда: целочисленный ключ 7 превратится в \"7\", и на чтении он уже не будет "
            "числом. Отдельные типы Python — дата, множество, кортеж — по умолчанию не поддерживаются: "
            "для них нужен либо перевод в строку на границе, либо обработчик по умолчанию. "
            "Флаг ensure_ascii решает, экранировать ли некириллические символы, а разделители задают "
            "пробелы между элементами: это меняет только вид строки, но не её смысл."
        ),
        example=_JSON_EXAMPLE,
        example_output=_JSON_OUTPUT,
        checkpoint_prompt="Что произойдёт, если в словаре вместо None оставить строку \"None\"?",
        checkpoint_choices=(
            "В JSON попадёт строка, и клиент получит текст вместо отсутствующего значения",
            "В JSON попадёт null, потому что сериализатор угадает намерение",
            "В JSON попадёт число 0",
        ),
        misconception="В JSON можно положить любой тип Python, а разбираться с преобразованием будет клиент.",
        misconception_prompt=(
            "Возьми словарь с датой и множеством и объясни, что произойдёт при dumps без обработчика, "
            "а затем предложи, где именно должен жить перевод — на сервере или на клиенте."
        ),
        practice=(
            "Дан словарь, который сервер собирается отдать клиенту: "
            "`{\"created\": datetime(...), \"tags\": {\"a\", \"b\"}, \"count\": 3}`. "
            "Определи, какие значения пройдут через dumps без изменений, какие вызовут ошибку, "
            "и объясни, чем клиент отличит null от строки \"None\" в ответе. Отдельно разбери целочисленный "
            "ключ словаря и объясни, почему после loads он не окажется числом."
        ),
        conclusion=(
            "JSON хранит семь типов, поэтому None уходит как null, а даты, множества и кортежи "
            "требуют явного перевода на границе API."
        ),
        question="Как значение None из словаря Python попадёт в JSON?",
        choices=(
            "Как null",
            "Как строка \"None\"",
            "Как число 0",
        ),
        answer="Как null",
    ),
    _lesson(
        lesson_id="fastapi-basics-v1",
        title="FastAPI: приложение и первый эндпоинт",
        skill_id="backend.fastapi_basics",
        prerequisites=("backend.json", "python.functions"),
        difficulty=4,
        minutes=22,
        goal="Создать приложение FastAPI, описать эндпоинт функцией и проверить его ответ в тесте без запуска сервера.",
        theory=(
            "FastAPI строит маршруты из обычных функций Python: декоратор над функцией регистрирует путь "
            "и метод, а сама функция получает разобранные данные и возвращает значение, которое "
            "превращается в JSON-ответ. Тип возвращаемого значения подсказывает сериализатору, какой "
            "JSON получится, поэтому функция может возвращать словарь, не собирая строку вручную. "
            "Класс TestClient позволяет проверить эндпоинт в тесте: он принимает метод и путь и возвращает "
            "объект ответа с кодом, телом и заголовками, не поднимая сетевой порт. Такой тест не требует "
            "запущенного сервера и остаётся быстрым, но проверяет только код приложения: он не говорит о "
            "том, как приложение ведёт себя под настоящей нагрузкой."
        ),
        example=_FASTAPI_BASICS_EXAMPLE,
        example_output=_FASTAPI_BASICS_OUTPUT,
        checkpoint_prompt="Зачем в тесте используется TestClient, а не запуск сервера на порту?",
        checkpoint_choices=(
            "Он вызывает приложение напрямую, без порта и сети",
            "Он проверяет, что приложение выдерживает реальную нагрузку",
            "Он возвращает тело ответа как готовый Python-объект",
        ),
        misconception="TestClient проверяет приложение так же полно, как браузер с реальным сервером.",
        misconception_prompt=(
            "Назови два аспекта, которых TestClient не проверяет: один относится к сети, "
            "другой — к масштабированию. Объясни, почему отсутствие этих проверок не делает тест бесполезным."
        ),
        practice=(
            "Разбери эндпоинт, который объявлен так: "
            "`@app.get(\"/health\")` над функцией `def health() -> dict`, возвращающей "
            "`{\"status\": \"ok\"}`. Объясни по шагам, что произойдёт при вызове TestClient: "
            "какой код вернётся, как будет выглядеть тело и почему возвращаемое значение не нужно "
            "превращать в строку. Затем найди ошибку в варианте, где функция возвращает `dict`, "
            "а в декораторе указан метод `post`, и опиши последствия без готового исправления."
        ),
        conclusion=(
            "FastAPI превращает функцию в маршрут, а TestClient проверяет этот маршрут без порта и сети, "
            "что делает тест быстрым, но не нагрузочным."
        ),
        question="Что делает декоратор app.get в приложении FastAPI?",
        choices=(
            "Регистрирует функцию как обработчик пути для метода GET",
            "Отправляет запрос на удалённый сервер",
            "Преобразует аргументы функции в JSON",
        ),
        answer="Регистрирует функцию как обработчик пути для метода GET",
    ),
    _lesson(
        lesson_id="fastapi-routing-v1",
        title="Маршруты: путь, параметр и 404",
        skill_id="backend.fastapi_routing",
        prerequisites=("backend.fastapi_basics",),
        difficulty=4,
        minutes=24,
        goal="Различать статический и параметризованный путь, читать сегмент пути в аргументе функции и объяснять, откуда берётся 404.",
        theory=(
            "Путь описывает форму ресурса, а сегмент в фигурных скобках объявляет параметр: функция "
            "обязана принять имя с таким же идентификатором. Порядок регистрации имеет значение, "
            "поэтому конкретный маршрут объявляют раньше параметризованного, иначе путь "
            "`/orders/summary` будет разобран как идентификатор заказа. Тип параметра объявляют "
            "аннотацией: FastAPI сам разбирает строку из пути и отвечает кодом 422, когда значение "
            "не соответствует типу, — это следствие проверки на границе, а не исключение обработчика. "
            "Отсутствие нужного ресурса обработчик выражает сам: в коде выше неизвестный идентификатор "
            "приводит к явному 404, и это решение автора обработчика, а не поведение по умолчанию."
        ),
        example=_FASTAPI_ROUTING_EXAMPLE,
        example_output=_FASTAPI_ROUTING_OUTPUT,
        checkpoint_prompt="Почему маршрут /orders/summary стоит объявлять раньше /orders/{order_id}?",
        checkpoint_choices=(
            "Иначе summary будет разобран как значение параметра order_id",
            "Иначе FastAPI не сможет построить схему OpenAPI",
            "Потому что конкретный путь короче параметризованного",
        ),
        misconception="Любой неверный формат сегмента пути приводит к 404.",
        misconception_prompt=(
            "Объясни, чем отличается код 404 от кода 422: какой из них говорит о неизвестном "
            "ресурсе, а какой — о неверном формате уже известного ресурса."
        ),
        practice=(
            "Дан набор маршрутов: `/orders`, `/orders/{order_id}`, `/orders/summary`, `/users/{user_id}`. "
            "Объясни, какой запрос вернёт 422, а какой 404, и в каком порядке их нужно регистрировать. "
            "Отдельно найди проблему в варианте, где обработчик принимает `user_id`, "
            "а в пути написано `{id}`, и опиши последствия. Не пиши готовый исправленный обработчик."
        ),
        conclusion=(
            "Параметр пути объявляется в фигурных скобках и обязан совпадать с аргументом функции, "
            "а конкретные пути регистрируются раньше параметризованных."
        ),
        question="Что произойдёт, если маршрут /orders/summary объявлен после /orders/{order_id}?",
        choices=(
            "Запрос к /orders/summary попадёт в обработчик заказа с order_id=\"summary\"",
            "FastAPI вернёт 500 при запуске приложения",
            "FastAPI вернёт 404 для обоих путей",
        ),
        answer="Запрос к /orders/summary попадёт в обработчик заказа с order_id=\"summary\"",
    ),
    _lesson(
        lesson_id="fastapi-dependencies-v1",
        title="Зависимости: общий код до обработчика",
        skill_id="backend.fastapi_dependencies",
        prerequisites=("backend.fastapi_routing",),
        difficulty=4,
        minutes=26,
        goal="Вынести повторяющуюся подготовку данных в зависимость, передать её значение в обработчик и подменить её в тесте.",
        theory=(
            "Зависимость — это обычная функция, значение которой подставляется в аргументы обработчика "
            "через Depends. Её вызов происходит до тела обработчика, и это удобное место для чтения "
            "сессии, определения текущего пользователя или получения объекта по идентификатору. "
            "Ключевое правило: идентификатор пользователя приходит из сессии на сервере, поэтому "
            "зависимость возвращает его, а клиент не передаёт его в теле запроса. Зависимость "
            "объявляется один раз и переиспользуется, что убирает копирование кода из десятка "
            "обработчиков, но добавляет неявный шаг в поток запроса: читая обработчик, нужно знать, "
            "что именно он выполняет. В тестах зависимость подменяют через "
            "`dependency_overrides`, и такой подменённый вариант ничего не говорит о реальной "
            "логике определения пользователя — её проверяют отдельно."
        ),
        example=_FASTAPI_DEPENDENCIES_EXAMPLE,
        example_output=_FASTAPI_DEPENDENCIES_OUTPUT,
        checkpoint_prompt="Где берётся значение tenant, которое получает обработчик?",
        checkpoint_choices=(
            "Из функции, зарегистрированной через Depends, до тела обработчика",
            "Из тела запроса, если клиент его прислал",
            "Из глобальной переменной, если клиент её не прислал",
        ),
        misconception="Тест с подменённой зависимостью доказывает, что проверка доступа работает правильно.",
        misconception_prompt=(
            "Объясни, что именно остаётся непроверенным, когда настоящая зависимость заменена "
            "на функцию, всегда возвращающую одну и ту же строку."
        ),
        practice=(
            "Даны два обработчика, и оба начинаются с одинаковых четырёх строк: чтение сессии, "
            "поиск текущего пользователя, проверка его прав и выбор базы данных. Объясни, что "
            "именно выносится в зависимость, что остаётся в обработчике и почему проверку прав "
            "не стоит прятать внутри зависимости. Затем найди ошибку в варианте, где зависимость "
            "принимает `user_id` из тела запроса, и опиши, чем это опасно. Готовое решение не пиши."
        ),
        conclusion=(
            "Зависимость выполняется до обработчика, получает данные из сессии на сервере и может "
            "быть подменена в тесте, но подмена ничего не проверяет о её собственном коде."
        ),
        question="Когда FastAPI вызывает функцию, переданную через Depends?",
        choices=(
            "До выполнения тела обработчика",
            "После того как обработчик вернёт ответ",
            "Только если обработчик сам её вызовет",
        ),
        answer="До выполнения тела обработчика",
    ),
    _lesson(
        lesson_id="request-validation-v1",
        title="Валидация входных данных на границе",
        skill_id="backend.request_validation",
        prerequisites=("backend.fastapi_dependencies",),
        difficulty=5,
        minutes=26,
        goal="Описать модель входа с явными ограничениями и объяснить, почему неизвестное поле должно отклоняться.",
        theory=(
            "Входные данные — недоверенный ввод: клиент может прислать лишний ключ, строку вместо "
            "числа или значение вне диапазона. Модель входа объявляет типы и границы, а проверка "
            "выполняется до тела обработчика: если модель не прошла, обработчик не вызывается вовсе. "
            "Ограничения задают явно — длину строки, нижнюю и верхнюю границу числа, — иначе "
            "поле принимает любую строку и ошибка всплывает глубже в домене. Политика extra "
            "определяет судьбу неизвестных полей: `forbid` отклоняет запрос, а разрешающая политика "
            "молча выбросит поле, и клиент не заметит, что отправил его напрасно. Дополнительно "
            "полезно ограничивать тело запроса по размеру на уровне сервера, иначе ограничения модели "
            "проверяются уже после того, как тело прочитано в память. Ответ 422 означает, что запрос "
            "разобран и отклонён проверкой формы, а 400 — что запрос не удалось разобрать вовсе."
        ),
        example=_REQUEST_VALIDATION_EXAMPLE,
        example_output=_REQUEST_VALIDATION_OUTPUT,
        checkpoint_prompt="Почему неизвестное поле в теле запроса лучше отклонять, а не игнорировать?",
        checkpoint_choices=(
            "Иначе клиент будет считать, что поле сохранено, хотя сервер его отбросил",
            "Иначе тело запроса станет слишком большим",
            "Иначе обработчик не сможет прочитать известные поля",
        ),
        misconception="Если обработчик не читает поле, то и проверять его не нужно.",
        misconception_prompt=(
            "Приведи случай, где клиент отправляет опечатку в имени поля, а сервер молча её "
            "игнорирует, и объясни, почему это дороже от явного отклонения."
        ),
        practice=(
            "Разбери модель `OrderIn` с полями `email` и `quantity`, где email ограничен по длине, "
            "а quantity — диапазоном от 1 до 100, и неизвестные поля запрещены. Объясни по шагам, "
            "какой код ответа получит клиент в четырёх случаях: корректные данные, пустой email, "
            "quantity равна 0, лишний ключ. Затем найди дыру: что произойдёт, если тело запроса "
            "будет очень большим, — и объясни, на каком уровне это ограничивается."
        ),
        conclusion=(
            "Модель входа проверяется до обработчика, а extra=\"forbid\" превращает опечатку клиента "
            "в явный ответ вместо тихой потери данных."
        ),
        question="Что произойдёт, если тело запроса не проходит валидацию модели входа?",
        choices=(
            "Ответ 422 и тело обработчика не выполняется",
            "Обработчик выполнится и сам исправит значения",
            "Ответ 500 из-за ошибки валидации",
        ),
        answer="Ответ 422 и тело обработчика не выполняется",
    ),
    _lesson(
        lesson_id="response-models-v1",
        title="Модель ответа: что сервер отдаёт клиенту",
        skill_id="backend.response_models",
        prerequisites=("backend.request_validation",),
        difficulty=4,
        minutes=24,
        goal="Отделить модель строки в базе от модели ответа и объяснить, почему лишние поля не должны попадать к клиенту.",
        theory=(
            "Модель ответа описывает форму данных, которые видит клиент, и она намеренно уже модели "
            "хранения. Строка в базе может содержать хеш пароля, внутренний идентификатор или служебную "
            "отметку, и всё это не должно попадать в ответ: клиенту не нужен хеш, а его утечка — "
            "дыра. Объявление `response_model` заставляет сериализатор собрать ответ по модели ответа, "
            "и поля, которых в ней нет, просто не отправляются. Возвращать можно объект модели "
            "хранения — сериализатор прочитает нужные поля сам, поэтому дублировать сборку ответа "
            "вручную не нужно. Вторая причина для отдельной модели ответа — форма ответа меняется "
            "независимо от схемы таблицы: переименование колонки не должно ломать клиентов, а "
            "добавление новой модели ответа для этого достаточно."
        ),
        example=_RESPONSE_MODELS_EXAMPLE,
        example_output=_RESPONSE_MODELS_OUTPUT,
        checkpoint_prompt="Что произойдёт с полем password_hash из модели хранения при сериализации по модели ответа?",
        checkpoint_choices=(
            "Оно не попадёт в ответ, потому что в модели ответа такого поля нет",
            "Оно попадёт в ответ, но будет обрезано",
            "Оно попадёт в ответ под другим именем",
        ),
        misconception="Достаточно вернуть из обработчика словарь с нужными полями, отдельная модель ответа не нужна.",
        misconception_prompt=(
            "Объясни, какую ошибку допустит обработчик, возвращающий словарь, собранный вручную "
            "из строки базы, и как её сложнее заметить при росте числа полей."
        ),
        practice=(
            "Дана строка хранения с полями `id`, `email` и `password_hash`, и две модели: "
            "модель хранения со всеми тремя полями и модель ответа только с `id` и `email`. "
            "Объясни, почему обработчик может вернуть объект модели хранения и получить правильный "
            "ответ, и найди риск в варианте, где обработчик возвращает `dict(row)`: какие поля "
            "и почему окажутся в ответе. Затем реши, что должно произойти при добавлении в таблицу "
            "новой колонки `is_active`, и в каком направлении придётся менять контракт."
        ),
        conclusion=(
            "Модель ответа уже модели хранения, и сериализация по ней не отправляет клиенту "
            "хеши паролей и внутренние поля."
        ),
        question="Зачем нужна отдельная модель ответа, если обработчик может вернуть словарь?",
        choices=(
            "Чтобы модель ответа не раскрывала клиенту поля модели хранения",
            "Чтобы обработчик не мог вернуть ничего лишнего по ошибке",
            "Чтобы сериализатор не проверял типы",
        ),
        answer="Чтобы модель ответа не раскрывала клиенту поля модели хранения",
    ),
)
