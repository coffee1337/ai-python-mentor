"""New corrected publications; the original v1 authoring remains historical."""
from copy import deepcopy


def corrected_lessons(lessons):
    originals = {lesson['id']: lesson for lesson in lessons}
    imports = deepcopy(originals['imports-v1'])
    imports['id'], imports['version'] = 'imports-v2', '2'
    imports['checkpoint']['choices'] = [
        'Локальный псевдоним меняет способ обращения, сохраняя исходное имя в модуле',
        'Псевдоним переименовывает атрибут внутри импортируемого модуля',
        'Псевдоним копирует исходный код модуля',
    ]
    fixtures = deepcopy(originals['fixtures-v1'])
    fixtures['id'], fixtures['version'] = 'fixtures-v2', '2'
    fixtures['theory'] = ('Pytest yield-фикстура передаёт подготовленный ресурс тесту, затем выполняет teardown после yield. '
        'Если подготовка упала до yield, этот teardown не зарегистрирован: ранее открытые ресурсы нужно защитить отдельно. '
        'У contextlib.contextmanager освобождение при исключении в with гарантирует try/finally вокруг yield; один код после yield этого не гарантирует.')
    fixtures['example'] = 'from contextlib import contextmanager\n@contextmanager\ndef session():\n    print("open")\n    try:\n        yield "db"\n    finally:\n        print("close")\nwith session() as resource:\n    print("use", resource)'
    fixtures['conclusion'] = 'В contextmanager защищайте освобождение через try/finally. У pytest отдельно учитывайте ошибку подготовки до yield.'
    fixtures['question'] = 'Что гарантирует cleanup в contextmanager при исключении внутри with?'
    fixtures['choices'] = ['try/finally вокруг yield', 'Любой код после yield без finally', 'Возврат ресурса через return']
    fixtures['answer'] = fixtures['choices'][0]
    fixtures['checkpoint'] = {'prompt': fixtures['question'], 'choices': fixtures['choices'][:]}
    fixtures['misconception_check'] = {'misconception': 'Код после yield в contextmanager всегда выполняется без finally', 'prompt': 'Проследите, куда будет выброшено исключение из with, и объясните необходимость finally.'}
    fixtures['body'] = f"Цель: {fixtures['goal']}\n\n{fixtures['theory']}\n\n{fixtures['practice']}\n\n{fixtures['conclusion']}"
    return (imports, fixtures)


CORRECTED_CHECKS = {
    'imports-v2': (
        {'id':'imports-alias-v2','prompt':'Что делает from datetime import timedelta as span?',
         'choices':['Связывает локальное имя span с timedelta','Переименовывает datetime.timedelta в исходном модуле','Копирует исходный код timedelta'],
         'answer':'Связывает локальное имя span с timedelta','explanation':'as создаёт локальную привязку; импортируемый модуль не переименовывается.',
         'choice_explanations':{'Связывает локальное имя span с timedelta':'Именно локальная привязка меняется через as.','Переименовывает datetime.timedelta в исходном модуле':'Имя timedelta в datetime остаётся прежним.','Копирует исходный код timedelta':'Импорт связывает объект с именем; исходный код не копируется.'}},
        {'id':'imports-qualified-v2','prompt':'После import math как обратиться к sqrt?',
         'choices':['math.sqrt(9)','sqrt(9) без другого импорта','math(9)'], 'answer':'math.sqrt(9)',
         'explanation':'import math связывает имя модуля; атрибут читается через точку.',
         'choice_explanations':{'math.sqrt(9)':'sqrt — атрибут импортированного модуля.','sqrt(9) без другого импорта':'import math не создаёт отдельное локальное имя sqrt.','math(9)':'Модуль math не вызывается как функция.'}},
    ),
    'fixtures-v2': (
        {'id':'fixtures-finally-v2','prompt':'Где гарантировать cleanup у contextmanager, если with выбрасывает исключение?',
         'choices':['В finally вокруг yield','Только после yield без finally','До yield'], 'answer':'В finally вокруг yield',
         'explanation':'Исключение из with выбрасывается в точке yield, и finally выполняется при выходе.',
         'choice_explanations':{'В finally вокруг yield':'finally выполняется и при исключении.','Только после yield без finally':'Исключение может пропустить обычный код после yield.','До yield':'Тогда ресурс будет освобождён до использования.'}},
        {'id':'fixtures-setup-v2','prompt':'Подготовка pytest yield-фикстуры упала до yield. Выполнится ли teardown после yield?',
         'choices':['Нет: для этого ресурса нужно отдельно защитить подготовку','Да: yield уже зарегистрирован','Да: pytest автоматически найдёт любой close'],
         'answer':'Нет: для этого ресурса нужно отдельно защитить подготовку', 'explanation':'Фикстура ещё не дошла до yield, поэтому её teardown не зарегистрирован.',
         'choice_explanations':{'Нет: для этого ресурса нужно отдельно защитить подготовку':'Защитите уже открытый ресурс через finally или явно зарегистрированный finalizer.','Да: yield уже зарегистрирован':'До точки yield регистрация этого teardown не произошла.','Да: pytest автоматически найдёт любой close':'Pytest не вызывает произвольные close автоматически.'}},
    ),
}


def corrected_ladders(legacy):
    imports = deepcopy(legacy['imports-v1'])
    imports['version'], imports['lesson_id'] = 2, 'imports-v2'
    fixtures = {'version':2,'lesson_id':'fixtures-v2','skill_id':'python.fixtures','hints':(
        (1,'direction','Рассмотрите обычный выход и выход с исключением как два отдельных пути.'),
        (2,'concept','Исключение из тела with возвращается в генератор в точке его приостановки.'),
        (3,'step','Проследите переход от приостановки генератора к обработке исключения и освобождению ресурса.'),
        (4,'pseudocode','открыть ресурс\nзащитить область передачи ресурса\nпри любом выходе выполнить освобождение'),
        (5,'solution','Оборачивайте yield в try/finally и освобождайте ресурс в finally. Для ошибки подготовки pytest до yield защищайте уже открытые ресурсы отдельно.'),
    )}
    return {'imports-v2':imports,'fixtures-v2':fixtures}
