"""Versioned authored questions mapped only to skills taught in the current course.

Every question resolves to a skill in the authored graph.  Two questions per
`python.core` skill: an ``anchor`` near the skill difficulty and a ``probe``
slightly above it, so the adaptive branch measures recognition and
application separately.  ``MAX_QUESTIONS`` bounds a single run; the bank is the
whole pool the branch chooses from.

Authored question ids are immutable once published, so the six questions from
the first course wave keep their ids, texts, answers and difficulties.  They are
listed in ``LEGACY_DIFFICULTY_EXEMPT`` below because their difficulty predates
the anchor/probe range rule.
"""
from app.skill_graph import SKILLS

# Published before the anchor/probe difficulty range existed.  Their ids,
# prompts, choices, answers and difficulties must not change.
LEGACY_DIFFICULTY_EXEMPT = frozenset(
    {
        "variables-v1",
        "types-v1",
        "conditions-v1",
        "boolean-v1",
        "assignment-v1",
        "branch-v1",
    }
)

MIN_DIFFICULTY = 0.1
MAX_DIFFICULTY = 0.9
# Every non-legacy question sits inside its own skill's difficulty range, so a
# single answer is evidence about that skill and not about a neighbouring one.
# Legacy questions from the first course wave are exempt and keep their
# published difficulty.
DIFFICULTY_TOLERANCE = 0.08

_CORE_SKILL_IDS = tuple(
    skill["id"] for skill in SKILLS if skill["category"] == "python.core"
)
SKILL_IDS = frozenset(skill["id"] for skill in SKILLS)
SKILL_DIFFICULTY = {skill["id"]: skill["difficulty"] for skill in SKILLS}
SKILL_ORDER = {skill_id: index for index, skill_id in enumerate(_CORE_SKILL_IDS)}


def validate_bank(questions):
    """Reject a malformed or graph-orphaned bank before it can be served."""
    seen: set[str] = set()
    for question in questions:
        question_id = question.get("id")
        if not isinstance(question_id, str) or not question_id.endswith("-v1"):
            raise ValueError("Diagnostic question id must be a -v1 string")
        if question_id in seen:
            raise ValueError("Duplicate diagnostic question id")
        seen.add(question_id)
        skill_id = question.get("skill_id")
        if skill_id not in SKILL_IDS:
            raise ValueError("Diagnostic question references a missing skill")
        if skill_id not in SKILL_ORDER:
            raise ValueError("Diagnostic question must target a python.core skill")
        prompt = question.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Diagnostic question requires a prompt")
        choices = question.get("choices")
        if (
            not isinstance(choices, list)
            or len(choices) < 2
            or not all(isinstance(choice, str) and choice for choice in choices)
            or len(set(choices)) != len(choices)
        ):
            raise ValueError("Diagnostic question choices must be unique strings")
        if question.get("answer") not in choices:
            raise ValueError("Diagnostic question answer must be one of its choices")
        difficulty = question.get("difficulty")
        if isinstance(difficulty, bool) or not isinstance(difficulty, (int, float)):
            raise ValueError("Diagnostic question difficulty must be a number")
        if not MIN_DIFFICULTY <= difficulty <= MAX_DIFFICULTY:
            raise ValueError("Diagnostic question difficulty is out of bounds")
        if question_id not in LEGACY_DIFFICULTY_EXEMPT:
            skill_difficulty = SKILL_DIFFICULTY[skill_id]
            if abs(difficulty - skill_difficulty) > DIFFICULTY_TOLERANCE:
                raise ValueError("Diagnostic question difficulty is outside its skill range")
    missing = [
        skill_id for skill_id in _CORE_SKILL_IDS
        if not any(question["skill_id"] == skill_id for question in questions)
    ]
    if missing:
        raise ValueError("Diagnostic bank does not cover every python.core skill")


def skill_order(question):
    """Deterministic ordering key: graph position, then question id."""
    return (SKILL_ORDER[question["skill_id"]], question["id"])

QUESTIONS = (
 {"id": "variables-reassign-v1", "skill_id": "python.variables", "difficulty": 0.1, "prompt": "Что выведет код: `count = 4; count = count + 2; print(count)`?", "choices": ["6", "4", "2"], "answer": "6"},
 {"id": "variables-v1", "skill_id": "python.variables", "difficulty": 0.15, "prompt": "Что выведет: count = 4; count = count + 2; print(count)?", "choices": ["4", "6", "2"], "answer": "6"},
 {"id": "types-v1", "skill_id": "python.variables", "difficulty": 0.25, "prompt": "Какое значение хранит переменная после price = 3.14?", "choices": ["3.14", "string value", "None"], "answer": "3.14"},
 {"id": "assignment-v1", "skill_id": "python.variables", "difficulty": 0.55, "prompt": "Чему равен x после x = 5; x = x * 2?", "choices": ["5", "10", "25"], "answer": "10"},
 {"id": "data-types-cast-v1", "skill_id": "python.data_types", "difficulty": 0.1, "prompt": "Что вернёт `type(3.14).__name__`?", "choices": ["float", "int", "str"], "answer": "float"},
 {"id": "data-types-convert-v1", "skill_id": "python.data_types", "difficulty": 0.16, "prompt": "Если `port = \"8000\"`, какой тип имеет `port`?", "choices": ["str", "int", "Тип с меняется на int"], "answer": "str"},
 {"id": "conditions-chain-v1", "skill_id": "python.conditionals", "difficulty": 0.2, "prompt": "Что выведет код: `age = 18; if age > 18: print(\"adult\") else: print(\"minor\")`?", "choices": ["minor", "adult", "Ничего не выведет"], "answer": "minor"},
 {"id": "conditions-v1", "skill_id": "python.conditionals", "difficulty": 0.35, "prompt": "Какая ветка выполняется при age = 18 в условии age >= 18?", "choices": ["adult", "minor", "обе"], "answer": "adult"},
 {"id": "boolean-v1", "skill_id": "python.conditionals", "difficulty": 0.45, "prompt": "Как проверить, что количество равно нулю или больше?", "choices": ["count >= 0", "count = 0", "count < 0"], "answer": "count >= 0"},
 {"id": "branch-v1", "skill_id": "python.conditionals", "difficulty": 0.65, "prompt": "При score = 80 сработает ли if score > 80?", "choices": ["Да", "Нет", "Зависит от типа"], "answer": "Нет"},
 {"id": "loops-range-v1", "skill_id": "python.loops", "difficulty": 0.16, "prompt": "Что выведет код: `for i in range(3): print(i)`?", "choices": ["0, 1, 2 каждый с новой строки", "1, 2, 3 каждый с новой строки", "Только 3"], "answer": "0, 1, 2 каждый с новой строки"},
 {"id": "loops-accumulate-v1", "skill_id": "python.loops", "difficulty": 0.22, "prompt": "Что напечатает код: `total = 0; for n in [1, 2, 3]: total = total + n; print(total)`?", "choices": ["6", "3", "0"], "answer": "6"},
 {"id": "functions-call-v1", "skill_id": "python.functions", "difficulty": 0.18, "prompt": "Что делает вызов функции без `return`?", "choices": ["Возвращает значение None", "Возвращает 0", "Ничего не возвращает и не выполняется"], "answer": "Возвращает значение None"},
 {"id": "functions-default-flow-v1", "skill_id": "python.functions", "difficulty": 0.24, "prompt": "Что произойдёт после выполнения `print` внутри функции, если есть `return` ниже?", "choices": ["Сначала напечатает, затем вернёт значение", "Вернёт значение без печати", "Печать отменит возвращаемое значение"], "answer": "Сначала напечатает, затем вернёт значение"},
 {"id": "parameters-args-v1", "skill_id": "python.parameters", "difficulty": 0.2, "prompt": "Сколько аргументов примет функция с сигнатурой `def f(a, b)`?", "choices": ["Два обязательных", "Один обязательный", "Любое количество"], "answer": "Два обязательных"},
 {"id": "parameters-kwargs-v1", "skill_id": "python.parameters", "difficulty": 0.26, "prompt": "Что даёт `**kwargs` в сигнатуре функции?", "choices": ["Собирает именованные аргументы в словарь", "Превращает словарь в список", "Умножает все аргументы"], "answer": "Собирает именованные аргументы в словарь"},
 {"id": "return-values-implicit-v1", "skill_id": "python.return_values", "difficulty": 0.22, "prompt": "Что вернёт функция без оператора `return`?", "choices": ["None", "0", "Пустую строку"], "answer": "None"},
 {"id": "return-values-tuple-v1", "skill_id": "python.return_values", "difficulty": 0.28, "prompt": "Как вернуть из функции сразу два значения?", "choices": ["Вернуть кортеж из двух элементов", "Напечатать их по очереди", "Вызвать `return` дважды"], "answer": "Вернуть кортеж из двух элементов"},
 {"id": "scope-global-read-v1", "skill_id": "python.scope", "difficulty": 0.24, "prompt": "Видна ли переменная, объявленная снаружи функции, внутри неё?", "choices": ["Да, её можно прочитать", "Нет, только с ключевым словом global", "Нет, переменные видны только в своём блоке"], "answer": "Да, её можно прочитать"},
 {"id": "scope-name-error-v1", "skill_id": "python.scope", "difficulty": 0.3, "prompt": "Что произойдёт при обращении к переменной, которой нигде нет?", "choices": ["Возникнет ошибка NameError", "Вернётся None", "Вернётся пустая строка"], "answer": "Возникнет ошибка NameError"},
 {"id": "mutability-list-shared-v1", "skill_id": "python.mutability", "difficulty": 0.26, "prompt": "Изменится ли второй список, если первый добавили в него через `append`?", "choices": ["Да, потому что это ссылка на тот же список", "Нет, списки копируются", "Изменится только сам элемент списка"], "answer": "Да, потому что это ссылка на тот же список"},
 {"id": "mutability-copy-v1", "skill_id": "python.mutability", "difficulty": 0.32, "prompt": "Какой способ даёт независимую копию списка?", "choices": ["Взять срез списка целиком", "Присвоить имя другого списка", "Вызвать `append`"], "answer": "Взять срез списка целиком"},
 {"id": "strings-index-v1", "skill_id": "python.strings", "difficulty": 0.28, "prompt": "Что вернёт `\"python\"[0]`?", "choices": ["Символ p", "Слово python", "Символ o"], "answer": "Символ p"},
 {"id": "strings-slice-v1", "skill_id": "python.strings", "difficulty": 0.34, "prompt": "Что вернёт `\"abcdef\"[1:3]`?", "choices": ["Символы b и c", "Символы a и b", "Символы b, c и d"], "answer": "Символы b и c"},
 {"id": "numbers-int-division-v1", "skill_id": "python.numbers", "difficulty": 0.3, "prompt": "Что вернёт `7 / 2` в Python 3?", "choices": ["3.5", "3", "4"], "answer": "3.5"},
 {"id": "numbers-round-v1", "skill_id": "python.numbers", "difficulty": 0.36, "prompt": "Что сделает `round(2.7)`?", "choices": ["Вернёт 3", "Вернёт 2.7", "Вернёт 4"], "answer": "Вернёт 3"},
 {"id": "booleans-comparison-v1", "skill_id": "python.booleans", "difficulty": 0.32, "prompt": "Какой тип у результата сравнения `1 < 2`?", "choices": ["bool", "int", "str"], "answer": "bool"},
 {"id": "booleans-chain-v1", "skill_id": "python.booleans", "difficulty": 0.38, "prompt": "Что вернёт сравнение `0 == False`?", "choices": ["Истину", "Ложь", "Ошибку"], "answer": "Истину"},
 {"id": "truthiness-empty-v1", "skill_id": "python.truthiness", "difficulty": 0.34, "prompt": "Какое значение ложно в условии `if`?", "choices": ["Пустая строка и ноль", "Любое непустое число", "Только пустой список"], "answer": "Пустая строка и ноль"},
 {"id": "truthiness-custom-v1", "skill_id": "python.truthiness", "difficulty": 0.4, "prompt": "Сработает ли `if` для непустой строки?", "choices": ["Да, непустая строка истинна", "Нет, строки всегда ложны", "Сработает только для нуля"], "answer": "Да, непустая строка истинна"},
 {"id": "comprehensions-basic-v1", "skill_id": "python.comprehensions", "difficulty": 0.36, "prompt": "Что вернёт `[n * 2 for n in [1, 2, 3]]`?", "choices": ["Список [2, 4, 6]", "Список [1, 2, 3]", "Число 6"], "answer": "Список [2, 4, 6]"},
 {"id": "comprehensions-conditional-v1", "skill_id": "python.comprehensions", "difficulty": 0.42, "prompt": "Как оставить в списке только чётные числа?", "choices": ["Добавить условие после элемента в генераторе", "Отсортировать список", "Преобразовать список в множество"], "answer": "Добавить условие после элемента в генераторе"},
 {"id": "lists-append-v1", "skill_id": "python.lists", "difficulty": 0.38, "prompt": "Как добавить элемент в конец списка?", "choices": ["Методом `append`", "Оператором `+`", "Методом `sort`"], "answer": "Методом `append`"},
 {"id": "lists-mutate-v1", "skill_id": "python.lists", "difficulty": 0.44, "prompt": "Изменится ли сам список после `items = items + [3]`?", "choices": ["Нет, пересоздаётся новое имя списка", "Да, список меняется на месте всегда", "Список превратится в кортеж"], "answer": "Нет, пересоздаётся новое имя списка"},
 {"id": "tuples-unpack-v1", "skill_id": "python.tuples", "difficulty": 0.4, "prompt": "Что делает `code, label = (200, \"OK\")`?", "choices": ["Распаковывает кортеж в две переменные", "Создаёт словарь", "Соединяет значения в строку"], "answer": "Распаковывает кортеж в две переменные"},
 {"id": "tuples-immutable-v1", "skill_id": "python.tuples", "difficulty": 0.46, "prompt": "Что будет при попытке изменить элемент кортежа?", "choices": ["Возникнет ошибка, элемент не изменится", "Элемент изменится", "Кортеж превратится в список"], "answer": "Возникнет ошибка, элемент не изменится"},
 {"id": "sets-membership-v1", "skill_id": "python.sets", "difficulty": 0.42, "prompt": "Что проверит выражение `\"GET\" in {\"GET\", \"POST\"}`?", "choices": ["Есть ли такое значение в наборе", "Сколько элементов в наборе", "Порядок элементов набора"], "answer": "Есть ли такое значение в наборе"},
 {"id": "sets-dedupe-v1", "skill_id": "python.sets", "difficulty": 0.48, "prompt": "Зачем хранить набор разрешённых методов во множестве?", "choices": ["Чтобы значения не повторялись", "Чтобы сохранить порядок", "Чтобы хранить пары ключ-значение"], "answer": "Чтобы значения не повторялись"},
 {"id": "dictionaries-key-v1", "skill_id": "python.dictionaries", "difficulty": 0.44, "prompt": "Как прочитать значение по ключу `data[\"id\"]`?", "choices": ["Обратиться к словарю по этому ключу", "Найти индекс элемента в списке", "Вызвать функцию словаря"], "answer": "Обратиться к словарю по этому ключу"},
 {"id": "dictionaries-default-v1", "skill_id": "python.dictionaries", "difficulty": 0.5, "prompt": "Что сделает `data.get(\"email\", \"unknown\")`, если ключа нет?", "choices": ["Вернёт \"unknown\"", "Вернёт пустой словарь", "Поднимет KeyError"], "answer": "Вернёт \"unknown\""},
 {"id": "slicing-basic-v1", "skill_id": "python.slicing", "difficulty": 0.46, "prompt": "Что вернёт `\"abcdef\"[1:4]`?", "choices": ["Символы b, c, d", "Символы a, b, c", "Символы b, c, d, e"], "answer": "Символы b, c, d"},
 {"id": "slicing-negative-step-v1", "skill_id": "python.slicing", "difficulty": 0.52, "prompt": "Что сделает срез с отрицательным шагом, например `values[::-1]`?", "choices": ["Развернёт порядок элементов", "Удалит последний элемент", "Отсортирует по убыванию"], "answer": "Развернёт порядок элементов"},
 {"id": "iteration-items-v1", "skill_id": "python.iteration", "difficulty": 0.48, "prompt": "Что даёт перебор словаря циклом `for key in data`?", "choices": ["Только ключи", "Пары ключ-значение", "Только значения"], "answer": "Только ключи"},
 {"id": "iteration-enumerate-v1", "skill_id": "python.iteration", "difficulty": 0.54, "prompt": "Зачем нужен `enumerate` при переборе?", "choices": ["Добавить порядковый номер к элементу", "Отсортировать элементы", "Преобразовать список в словарь"], "answer": "Добавить порядковый номер к элементу"},
 {"id": "exceptions-raise-v1", "skill_id": "python.exceptions", "difficulty": 0.5, "prompt": "Что делает оператор `raise`?", "choices": ["Прерывает выполнение и передаёт ошибку вверх", "Печатает текст ошибки и продолжает", "Создаёт объект без прерывания"], "answer": "Прерывает выполнение и передаёт ошибку вверх"},
 {"id": "exceptions-message-v1", "skill_id": "python.exceptions", "difficulty": 0.56, "prompt": "Зачем в сообщение ошибки включать конкретное значение?", "choices": ["Чтобы сразу было понятно, что исправлять", "Чтобы ошибка не печаталась", "Чтобы изменился тип ошибки"], "answer": "Чтобы сразу было понятно, что исправлять"},
 {"id": "try-except-order-v1", "skill_id": "python.try_except", "difficulty": 0.52, "prompt": "Что выполняется в блоке `except`?", "choices": ["Обработка ошибки указанного типа", "Повторный запуск блока `try`", "Вывод текста ошибки в консоль"], "answer": "Обработка ошибки указанного типа"},
 {"id": "try-except-finally-v1", "skill_id": "python.try_except", "difficulty": 0.58, "prompt": "Когда выполняется блок `finally`?", "choices": ["Всегда, независимо от того, была ли ошибка", "Только если ошибка была перехвачена", "Только если ошибки не было"], "answer": "Всегда, независимо от того, была ли ошибка"},
 {"id": "custom-exceptions-class-v1", "skill_id": "python.custom_exceptions", "difficulty": 0.54, "prompt": "Что даёт свой класс ошибки, наследующийся от Exception?", "choices": ["Доменную ошибку, которую можно обработать отдельно", "Более быстрый перехват ошибок", "Гарантию, что ошибка не возникнет"], "answer": "Доменную ошибку, которую можно обработать отдельно"},
 {"id": "custom-exceptions-raise-v1", "skill_id": "python.custom_exceptions", "difficulty": 0.6, "prompt": "Что произойдёт после `raise ValidationError(\"bad\")` внутри функции?", "choices": ["Выполнение функции прервётся", "Функция вернёт строку bad", "Функция напечатает bad и вернётся"], "answer": "Выполнение функции прервётся"},
 {"id": "modules-file-v1", "skill_id": "python.modules", "difficulty": 0.56, "prompt": "Что такое модуль в Python?", "choices": ["Файл с определениями, который импортируется по имени", "Папка с настройками проекта", "Отдельный процесс программы"], "answer": "Файл с определениями, который импортируется по имени"},
 {"id": "modules-main-v1", "skill_id": "python.modules", "difficulty": 0.62, "prompt": "Зачем в модуле проверяют условие запуска как главного файла?", "choices": ["Чтобы код выполнялся только при прямом запуске файла", "Чтобы модуль нельзя было импортировать", "Чтобы ускорить импорт"], "answer": "Чтобы код выполнялся только при прямом запуске файла"},
 {"id": "packages-init-v1", "skill_id": "python.packages", "difficulty": 0.58, "prompt": "Зачем каталогу пакета файл `__init__.py`?", "choices": ["Чтобы каталог распознавался как пакет", "Чтобы хранить в нём все тесты", "Чтобы имена импортировались автоматически"], "answer": "Чтобы каталог распознавался как пакет"},
 {"id": "packages-relative-v1", "skill_id": "python.packages", "difficulty": 0.64, "prompt": "Что означает импорт из своего пакета с одной точкой?", "choices": ["Импорт из текущего пакета", "Импорт из стандартной библиотеки", "Импорт из внешнего пакета"], "answer": "Импорт из текущего пакета"},
 {"id": "imports-alias-v1", "skill_id": "python.imports", "difficulty": 0.6, "prompt": "Что даёт импорт с переименованием, как `from a import b as c`?", "choices": ["Короткое понятное имя в коде", "Более быструю загрузку модуля", "Импорт всех имён модуля"], "answer": "Короткое понятное имя в коде"},
 {"id": "imports-from-v1", "skill_id": "python.imports", "difficulty": 0.66, "prompt": "Что даёт форма импорта одного имени из модуля?", "choices": ["Только указанное имя из модуля", "Весь модуль целиком", "Все встроенные имена"], "answer": "Только указанное имя из модуля"},
 {"id": "testing-basics-cases-v1", "skill_id": "python.testing_basics", "difficulty": 0.62, "prompt": "Зачем в проверке берут несколько случаев?", "choices": ["Чтобы увидеть поведение функции на разных входах", "Чтобы код выглядел длиннее", "Чтобы функция работала быстрее"], "answer": "Чтобы увидеть поведение функции на разных входах"},
 {"id": "testing-basics-failure-v1", "skill_id": "python.testing_basics", "difficulty": 0.68, "prompt": "Что делает сравнение фактического и ожидаемого результата?", "choices": ["Показывает, совпало ли поведение функции с ожиданием", "Меняет значение функции", "Считает скорость работы"], "answer": "Показывает, совпало ли поведение функции с ожиданием"},
 {"id": "assertions-usage-v1", "skill_id": "python.assertions", "difficulty": 0.64, "prompt": "Что делает `assert` при нарушении условия?", "choices": ["Поднимает AssertionError", "Печатает сообщение и продолжает", "Игнорирует условие"], "answer": "Поднимает AssertionError"},
 {"id": "assertions-optimized-v1", "skill_id": "python.assertions", "difficulty": 0.7, "prompt": "Чем опасно проверять ввод извне через `assert`?", "choices": ["Такую проверку можно отключить, и ошибка пройдёт незамеченной", "Проверка не принимает числа", "Проверка меняет значение переменной"], "answer": "Такую проверку можно отключить, и ошибка пройдёт незамеченной"},
 {"id": "pytest-basics-run-v1", "skill_id": "python.pytest_basics", "difficulty": 0.66, "prompt": "Что делает префикс `test_` в имени функции?", "choices": ["Позволяет pytest найти функцию при сборе тестов", "Возвращает результат проверки", "Отключает выполнение функции"], "answer": "Позволяет pytest найти функцию при сборе тестов"},
 {"id": "pytest-basics-select-v1", "skill_id": "python.pytest_basics", "difficulty": 0.72, "prompt": "Что будет, если тестовая функция не начнётся с `test_`?", "choices": ["pytest не включит её в набор тестов", "Функция выполнится дважды", "Функция вернёт ошибку компиляции"], "answer": "pytest не включит её в набор тестов"},
 {"id": "fixtures-scope-v1", "skill_id": "python.fixtures", "difficulty": 0.68, "prompt": "Где в фикстуре пишут освобождение ресурса?", "choices": ["После `yield`, чтобы оно выполнялось при выходе из блока", "До `yield`, чтобы освободить заранее", "В теле теста"], "answer": "После `yield`, чтобы оно выполнялось при выходе из блока"},
 {"id": "fixtures-yield-v1", "skill_id": "python.fixtures", "difficulty": 0.74, "prompt": "Зачем фикстуре `yield`?", "choices": ["Чтобы отдать ресурс в тело блока и выполнить код после выхода", "Чтобы функция ничего не возвращала", "Чтобы отключить проверки"], "answer": "Чтобы отдать ресурс в тело блока и выполнить код после выхода"},
 {"id": "typing-basics-annotation-v1", "skill_id": "python.typing_basics", "difficulty": 0.7, "prompt": "Что даёт аннотация типа аргумента?", "choices": ["Описывает ожидаемый тип для читателя и инструментов", "Проверяет тип при каждом вызове", "Преобразует значение в нужный тип"], "answer": "Описывает ожидаемый тип для читателя и инструментов"},
 {"id": "typing-basics-optional-v1", "skill_id": "python.typing_basics", "difficulty": 0.76, "prompt": "Что означает необязательный тип в подсказке результата?", "choices": ["Что функция может вернуть None, если данных нет", "Что функция обязана вернуть значение", "Что функция принимает любой тип"], "answer": "Что функция может вернуть None, если данных нет"},
 {"id": "type-hints-signature-v1", "skill_id": "python.type_hints", "difficulty": 0.72, "prompt": "Что фиксирует псевдоним словаря в подсказке типа?", "choices": ["Какие ключи и значения ожидаются в данных", "Сколько раз данные можно прочитать", "Как быстро работает код"], "answer": "Какие ключи и значения ожидаются в данных"},
 {"id": "type-hints-alias-v1", "skill_id": "python.type_hints", "difficulty": 0.78, "prompt": "Зачем описывать форму данных, приходящих снаружи?", "choices": ["Чтобы зафиксировать ожидаемый вид до работы с ними", "Чтобы данные стали отсортированными", "Чтобы словарь стал списком"], "answer": "Чтобы зафиксировать ожидаемый вид до работы с ними"},
 {"id": "dataclasses-declare-v1", "skill_id": "python.dataclasses", "difficulty": 0.74, "prompt": "Что даёт декоратор `@dataclass`?", "choices": ["Автоматически создаёт методы по полям", "Превращает класс в словарь", "Запрещает менять поля"], "answer": "Автоматически создаёт методы по полям"},
 {"id": "dataclasses-default-v1", "skill_id": "python.dataclasses", "difficulty": 0.8, "prompt": "Как задать значение по умолчанию для поля?", "choices": ["Присвоить его в объявлении поля", "Передать его после создания объекта", "Указать его в имени класса"], "answer": "Присвоить его в объявлении поля"},
 {"id": "classes-init-v1", "skill_id": "python.classes", "difficulty": 0.76, "prompt": "Что делает метод `__init__`?", "choices": ["Выполняется при создании экземпляра", "Выполняется при вызове класса как функции", "Выполняется при удалении объекта"], "answer": "Выполняется при создании экземпляра"},
 {"id": "classes-method-v1", "skill_id": "python.classes", "difficulty": 0.82, "prompt": "Как вызвать метод через объект?", "choices": ["Через точку: `объект.метод()`", "Через запятую в одной строке", "Просто по имени метода"], "answer": "Через точку: `объект.метод()`"},
 {"id": "objects-attribute-v1", "skill_id": "python.objects", "difficulty": 0.78, "prompt": "Как создать новый атрибут у объекта?", "choices": ["Присвоить значение: `объект.поле = значение`", "Вызвать `dict` от объекта", "Изменить имя класса"], "answer": "Присвоить значение: `объект.поле = значение`"},
 {"id": "objects-class-attribute-v1", "skill_id": "python.objects", "difficulty": 0.84, "prompt": "Чем атрибут класса отличается от атрибута экземпляра?", "choices": ["Атрибут класса общий для всех объектов", "Атрибут класса виден только одному объекту", "Различий нет"], "answer": "Атрибут класса общий для всех объектов"},
 {"id": "inheritance-override-v1", "skill_id": "python.inheritance", "difficulty": 0.8, "prompt": "Что произойдёт, если подкласс определит метод с тем же именем?", "choices": ["Метод подкласса перекроет метод родителя", "Выполнятся оба метода по очереди", "Получится ошибка компиляции"], "answer": "Метод подкласса перекроет метод родителя"},
 {"id": "inheritance-super-v1", "skill_id": "python.inheritance", "difficulty": 0.86, "prompt": "Зачем в методе подкласса вызывают `super()`?", "choices": ["Чтобы выполнить метод родителя", "Чтобы создать новый объект", "Чтобы ускорить выполнение"], "answer": "Чтобы выполнить метод родителя"},
 {"id": "composition-delegate-v1", "skill_id": "python.composition", "difficulty": 0.82, "prompt": "Как объект передаёт работу вложенному объекту?", "choices": ["Вызывает его метод и возвращает результат", "Копирует его поля себе", "Меняет класс вложенного объекта"], "answer": "Вызывает его метод и возвращает результат"},
 {"id": "composition-choose-v1", "skill_id": "python.composition", "difficulty": 0.88, "prompt": "Почему композицию часто предпочитают наследованию?", "choices": ["Объекты связаны снаружи, а не жёстко внутри иерархии", "Композиция всегда быстрее", "Композиция не требует классов"], "answer": "Объекты связаны снаружи, а не жёстко внутри иерархии"},
 {"id": "protocols-structure-v1", "skill_id": "python.protocols", "difficulty": 0.84, "prompt": "Что описывает протокол в подсказках типов?", "choices": ["Набор методов и свойств, которым должен соответствовать объект", "Конкретный класс с полями", "Порядок вызовов методов"], "answer": "Набор методов и свойств, которым должен соответствовать объект"},
 {"id": "protocols-runtime-v1", "skill_id": "python.protocols", "difficulty": 0.86, "prompt": "Что даёт проверка соответствия протоколу в рантайме?", "choices": ["Покажет, подходит ли объект по структуре", "Изменит класс объекта на структуру", "Ускорит вызовы методов"], "answer": "Покажет, подходит ли объект по структуре"},
 {"id": "decorators-wrap-v1", "skill_id": "python.decorators", "difficulty": 0.86, "prompt": "Что делает декоратор с функцией?", "choices": ["Оборачивает её в другую функцию, сохраняя вызов", "Выполняет её при импорте и всё", "Заменяет её телом цикла"], "answer": "Оборачивает её в другую функцию, сохраняя вызов"},
 {"id": "decorators-args-v1", "skill_id": "python.decorators", "difficulty": 0.88, "prompt": "Зачем декоратору принимать функцию в аргументе?", "choices": ["Чтобы обернуть её своим поведением", "Чтобы вызвать её при определении", "Чтобы ускорить её выполнение"], "answer": "Чтобы обернуть её своим поведением"},
 {"id": "generators-yield-v1", "skill_id": "python.generators", "difficulty": 0.88, "prompt": "Чем генератор отличается от обычной функции?", "choices": ["Отдаёт значения по одному через `yield`", "Всегда возвращает список", "Работает быстрее любой функции"], "answer": "Отдаёт значения по одному через `yield`"},
 {"id": "generators-send-v1", "skill_id": "python.generators", "difficulty": 0.9, "prompt": "Что делает `next` с генератором?", "choices": ["Получает очередное значение или останавливает его", "Отправляет значение в генератор и завершает его", "Перезапускает генератор с начала"], "answer": "Получает очередное значение или останавливает его"},
 {"id": "iterators-stop-v1", "skill_id": "python.iterators", "difficulty": 0.88, "prompt": "Что происходит, когда у итератора не осталось элементов?", "choices": ["Будет поднята ошибка остановки итерации", "Вернётся пустой список", "Итератор начнётся заново"], "answer": "Будет поднята ошибка остановки итерации"},
 {"id": "iterators-next-v1", "skill_id": "python.iterators", "difficulty": 0.9, "prompt": "Как получить следующий элемент итератора?", "choices": ["Вызвать `next` на объекте", "Обратиться к объекту по индексу", "Вызвать `len` на объекте"], "answer": "Вызвать `next` на объекте"},
 {"id": "context-managers-with-v1", "skill_id": "python.context_managers", "difficulty": 0.88, "prompt": "Что гарантирует блок `with`?", "choices": ["Код выхода выполнится при любом исходе блока", "Код внутри выполнится дважды", "Исключения внутри блока исчезнут"], "answer": "Код выхода выполнится при любом исходе блока"},
 {"id": "context-managers-enter-v1", "skill_id": "python.context_managers", "difficulty": 0.9, "prompt": "Какие методы определяет контекстный менеджер?", "choices": ["Вход при начале блока и выход при его завершении", "Только вход, выхода нет", "Ни входа, ни выхода"], "answer": "Вход при начале блока и выход при его завершении"},
)

MAX_QUESTIONS = 6
DIFFICULTY_PRIOR = {"beginner": 0.15, "student": 0.3, "junior": 0.45}
# One graph slot of difficulty per correct answer; the run walks the course
# order instead of jumping to the hardest question in the bank.
SLOT_STEP = 0.1
NEAR_SLOT_TOLERANCE = 0.02
FALLBACK_TOLERANCE = 0.1

QUESTIONS_BY_ID = {question["id"]: question for question in QUESTIONS}

validate_bank(QUESTIONS)
