import AppIcon from "./components/app-icon";

const stages = [
  {
    number: "01",
    title: "Первые строки Python",
    body: "Что такое программа, как читать код и зачем нужны переменные.",
  },
  {
    number: "02",
    title: "Уверенная база",
    body: "Условия, циклы, функции и работа с данными — с понятными примерами.",
  },
  {
    number: "03",
    title: "Веб и backend",
    body: "Как устроены сервер, запросы, API и базы данных.",
  },
  {
    number: "04",
    title: "Проектные этапы",
    body: "Соберите изученное в проектах и сохраняйте результаты работы.",
  },
];

export default function Home() {
  return (
    <main className="landing-shell">
      <header className="landing-header">
        <a className="brand" href="/">
          <span className="brand-mark">
            <AppIcon name="code" size={18} />
          </span>
          наставник<span className="brand-dot">.</span>
        </a>
        <nav aria-label="Навигация сайта">
          <a href="#program">Программа</a>
          <a href="#mentor">Как помогает AI</a>
          <a className="button-secondary" href="/auth">
            Войти <AppIcon name="arrow" size={16} />
          </a>
        </nav>
      </header>
      <section className="landing-hero">
        <div className="landing-hero-copy">
          <span className="landing-tag">
            <span aria-hidden="true" /> PYTHON · ОТ НУЛЯ К BACKEND
          </span>
          <h1>
            Первые строки кода.
            <br />
            <em>Понятный следующий шаг.</em>
          </h1>
          <p>
            Научитесь программировать на Python: объяснение, пример, небольшое
            задание. Персональный наставник поможет, когда что-то не
            складывается.
          </p>
          <div className="landing-actions">
            <a className="button" href="/auth">
              Начать с нуля <AppIcon name="arrow" size={18} />
            </a>
            <a className="landing-secondary-link" href="#program">
              Посмотреть программу
            </a>
          </div>
          <div className="landing-reassurance">
            <span>
              <AppIcon name="check" size={16} /> Опыт не нужен
            </span>
            <span>
              <AppIcon name="check" size={16} /> В вашем темпе
            </span>
            <span>
              <AppIcon name="check" size={16} /> Практика после объяснения
            </span>
          </div>
        </div>
        <div
          className="lesson-preview"
          aria-label="Пример того, как устроен урок"
        >
          <div className="preview-heading">
            <span className="preview-topic">
              <AppIcon name="book" size={18} /> Первый урок
            </span>
            <span className="badge">ОСНОВЫ PYTHON</span>
          </div>
          <div className="preview-content">
            <span className="page-kicker">СНАЧАЛА РАЗБЕРЁМСЯ</span>
            <h2>Как программа говорит «Привет»</h2>
            <p>
              <code>print</code> — команда, которая показывает текст на экране.
              Текст пишут в кавычках.
            </p>
            <div className="preview-code">
              <span>PYTHON</span>
              <pre>
                <code>
                  <span>print</span>(<em>"Привет, мир!"</em>)
                </code>
              </pre>
            </div>
            <div className="preview-output">
              <span>Результат программы</span>
              <strong>Привет, мир!</strong>
            </div>
            <div className="preview-mentor">
              <span className="tutor-icon">
                <AppIcon name="sparkles" size={20} />
              </span>
              <div>
                <strong>Непонятно, зачем кавычки?</strong>
                <p>Спросите наставника — он разберёт строку вместе с вами.</p>
              </div>
            </div>
          </div>
          <div className="preview-footer">
            <span>Разобраться → Попробовать → Закрепить</span>
            <AppIcon name="arrow" size={18} />
          </div>
        </div>
      </section>
      <section className="landing-program" id="program">
        <div className="landing-section-heading">
          <div>
            <span className="page-kicker">ПРОГРАММА ОБУЧЕНИЯ</span>
            <h2>От простого к тому, что вы хотите создавать</h2>
          </div>
          <p>
            Backend — часть приложения на сервере. Он принимает запросы,
            работает с данными и отправляет ответы. К этому придём после основ
            Python.
          </p>
        </div>
        <div className="landing-stage-grid">
          {stages.map((stage) => (
            <article key={stage.number}>
              <span>{stage.number}</span>
              <h3>{stage.title}</h3>
              <p>{stage.body}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="landing-mentor" id="mentor">
        <div className="landing-mentor-copy">
          <span className="page-kicker">КУРС + ПЕРСОНАЛЬНАЯ ПОМОЩЬ</span>
          <h2>
            Материал общий.
            <br />
            Ваши вопросы — свои.
          </h2>
          <p>
            В уроках есть проверенная основа. AI-наставник помогает объяснить её
            иначе, проследить пример по строкам и обсудить вашу ошибку. Он
            доступен в чате урока после подключения AI-сервиса.
          </p>
          <a className="button-secondary" href="/auth">
            Создать учебное пространство <AppIcon name="arrow" size={16} />
          </a>
        </div>
        <div className="mentor-example">
          <span className="badge">ПРИМЕР ВОПРОСА НАСТАВНИКУ</span>
          <blockquote>
            «Я ещё не понимаю, что такое переменная. Объясни на бытовом примере,
            а потом покажи одну строку кода».
          </blockquote>
          <p>Не нужно знать правильный термин, чтобы попросить помощи.</p>
        </div>
      </section>
      <footer className="landing-footer">
        <a className="brand" href="/">
          наставник<span className="brand-dot">.</span>
        </a>
        <span>Python Backend. Учиться, понимать, пробовать.</span>
        <a href="/auth">Войти в аккаунт →</a>
      </footer>
    </main>
  );
}
