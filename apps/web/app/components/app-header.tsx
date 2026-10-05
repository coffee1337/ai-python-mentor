export default function AppHeader() {
  return (
    <header className="topbar app-header">
      <a className="brand" href="/dashboard">↗ наставник<span className="brand-dot">.</span></a>
      <nav className="app-nav" aria-label="Разделы приложения">
        <a href="/dashboard">Обучение</a>
        <a href="/projects">Проекты</a>
        <a href="/jobs">Вакансии</a>
        <a href="/account">Аккаунт</a>
        <a href="/billing">Тариф</a>
      </nav>
    </header>
  );
}
