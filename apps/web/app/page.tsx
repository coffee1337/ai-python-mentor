const steps = ["Основы Python", "Работа с данными", "Web и API", "Backend-проекты"];

export default function Home() {
  return (
    <main className="shell">
      <header className="topbar"><a className="brand" href="#home"><span className="brand-mark">↗</span> наставник<span className="brand-dot">.</span></a><span className="top-note">PYTHON BACKEND · ПУТЬ НАЧИНАЕТСЯ ЗДЕСЬ</span></header>
      <section className="hero" id="home">
        <div className="hero-copy"><span className="eyebrow"><i /> ВАШ ПЕРСОНАЛЬНЫЙ AI-НАСТАВНИК</span><h1>От первого<br/>шага — к <em>Backend.</em></h1><p className="lead">Учитесь программировать на Python в своём темпе. Понятные объяснения, практика и путь к вашим целям — шаг за шагом.</p><a className="primary-button" href="/auth">Начать обучение <span>↘</span></a><div className="micro-copy">Без гонки. С пониманием того, что вы пишете.</div></div>
        <div className="visual" aria-label="Иллюстрация учебного маршрута"><div className="orb orb-one"/><div className="orb orb-two"/><div className="code-card"><div className="card-head"><span><b/> <b/> <b/></span><small>your_learning_path.py</small><span>•••</span></div><div className="code-lines"><p><span>01</span> <i># маленькие шаги, большой путь</i></p><p><span>02</span> <strong>goal</strong> = <em>"Python Backend"</em></p><p><span>03</span> <strong>while</strong> curious:</p><p><span>04</span> &nbsp;&nbsp;learn(<em>"something new"</em>)</p><p><span>05</span> &nbsp;&nbsp;build(<em>"real things"</em>)</p></div><div className="progress"><div><span>ВАШ МАРШРУТ</span><span>01 — 04</span></div><div className="progress-track"><i/></div></div></div><span className="float-label label-top">01 <b>ОСНОВА</b></span><span className="float-label label-bottom">✳ <b>ВАШ ТЕМП</b></span></div>
      </section>
      <section className="approach" id="approach"><div><span className="eyebrow">НЕ ПРОСТО КУРС</span><h2>Понимать важнее,<br/><em>чем просто пройти.</em></h2></div><p>Начинаем с основ Python и постепенно движемся к backend-разработке. Практика помогает закрепить знания, а наставник — разобраться в сложном.</p></section>
      <section className="path" aria-label="Направления обучения">{steps.map((step, i) => <div className="path-step" key={step}><span>0{i + 1}</span><b>{step}</b><i>↗</i></div>)}</section>
      <footer><span>НАЧИНАЕМ С PYTHON. СТРОИМ ОСНОВУ BACKEND.</span><span>Создано для обучения, шаг за шагом.</span></footer>
    </main>
  );
}
