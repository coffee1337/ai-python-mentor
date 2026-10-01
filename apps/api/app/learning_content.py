"""Small, versioned authored curriculum. Never execute learner input."""

LESSONS = (
    {
        "id": "variables-v1",
        "title": "Переменные и присваивание",
        "skill_id": "python.variables",
        "minutes": 10,
        "body": "Переменная связывает имя со значением. В backend так хранят, например, число запросов. Присваивание вычисляет правую часть и связывает результат с именем слева. Повторное присваивание заменяет значение, а не создаёт математическое равенство.",
        "example": "requests = 2\nrequests = requests + 1\nprint(requests)  # 3",
        "question": "Что выведет код: count = 4; count = count + 2; print(count)?",
        "choices": ["4", "6", "2"],
        "answer": "6",
    },
    {
        "id": "conditions-v1",
        "title": "Условия",
        "skill_id": "python.conditionals",
        "minutes": 10,
        "body": "Условие if выбирает действие, когда выражение истинно. Ветка else выполняется иначе. В backend это помогает выбрать ответ в зависимости от входных данных. Оператор >= включает равенство; > не включает. Отступы определяют тело ветки.",
        "example": 'age = 18\nif age >= 18:\n    print("adult")\nelse:\n    print("minor")',
        "question": 'Что выведет пример при age = 18?',
        "choices": ["adult", "minor", "Обе строки"],
        "answer": "adult",
    },
)
