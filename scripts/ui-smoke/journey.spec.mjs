import { test, expect } from "@playwright/test";

// Only disposable accounts on the local CI server. No real identities, delivery
// integrations, AI credentials, payments, or execution worker are configured.
async function capture(page, testInfo, name, workspace = false) {
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() =>
    window.scrollTo({ top: 0, left: 0, behavior: "instant" }),
  );
  await page.screenshot({
    path: testInfo.outputPath(`${name}.png`),
    fullPage: true,
  });
  const size = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: Math.max(
      document.documentElement.scrollWidth,
      document.body.scrollWidth,
    ),
  }));
  expect(
    size.document,
    `${name}: document must not scroll horizontally`,
  ).toBeLessThanOrEqual(size.viewport + 1);
  if (workspace && testInfo.project.name === "desktop") {
    const shell = await page.locator("main.dashboard-shell").boundingBox();
    const sidebar = await page.locator(".app-sidebar").boundingBox();
    expect(shell).not.toBeNull();
    expect(sidebar).not.toBeNull();
    expect(
      shell.width,
      `${name}: use available desktop workspace`,
    ).toBeGreaterThan((size.viewport - sidebar.width) * 0.9);
    expect(shell.x + shell.width).toBeGreaterThan(size.viewport - 8);
    const headingSize = await page
      .getByRole("heading", { level: 1 })
      .evaluate((node) => parseFloat(getComputedStyle(node).fontSize));
    expect(
      headingSize,
      `${name}: consistent readable workspace heading`,
    ).toBeLessThanOrEqual(44);
  }
}

async function openWorkspace(page, testInfo, route, heading, screenshot) {
  await page.goto(route);
  await expect(
    page.getByRole("heading", { level: 1, name: heading }),
  ).toBeVisible();
  await expect(page.locator(".workspace-bar")).toBeVisible();
  if (route === "/dashboard")
    await expect(
      page.locator(
        '.course-path-compact[aria-busy="false"] .course-next-lesson',
      ),
    ).toBeVisible();
  if (route === "/learning/path")
    await expect(
      page.locator('.course-path-full[aria-busy="false"]'),
    ).toBeVisible();
  if (route === "/account")
    await expect(page.locator('input[name="display_name"]')).toBeVisible();
  if (route === "/jobs")
    await expect(page.locator('input[name="title"]')).toBeVisible();
  if (route === "/projects")
    await expect(
      page
        .getByRole("button", { name: "Создать проект", exact: false })
        .first(),
    ).toBeVisible();
  if (route === "/billing")
    await expect(page.locator(".billing-plan-card").first()).toBeVisible();
  await capture(page, testInfo, screenshot, true);
}

test("beginner learns before questions and uses the personal workspace", async ({
  page,
}, testInfo) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  const name = `Новичок ${testInfo.project.name}`;
  const email = `browser-${testInfo.project.name}-${Date.now()}@example.invalid`;

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await capture(page, testInfo, "01-landing");
  await page.goto("/auth");
  await expect(
    page.getByRole("button", { name: "Создать аккаунт", exact: false }),
  ).toBeVisible();
  await capture(page, testInfo, "02-registration");
  await page.getByRole("button", { name: "Вход", exact: true }).click();
  await capture(page, testInfo, "03-login");
  await page.getByRole("button", { name: "Регистрация", exact: true }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page
    .getByLabel("Пароль", { exact: true })
    .fill("Only-Disposable-CI-Account-2026");
  await page
    .getByRole("button", { name: "Создать аккаунт", exact: false })
    .click();
  await expect(page).toHaveURL(/\/onboarding$/);
  await page.locator('input[name="display_name"]').fill(name);
  await page
    .locator('input[name="experience_level"][value="beginner"]')
    .check();
  await page.locator('input[name="weekly_minutes"]').fill("120");
  await capture(page, testInfo, "04-onboarding");
  await page
    .getByRole("button", { name: "Начать обучение", exact: false })
    .click();
  await expect(page).toHaveURL(/\/learning$/);

  const firstLesson = page.getByRole("heading", {
    level: 1,
    name: "С нуля: первая программа и переменные",
  });
  await expect(firstLesson).toBeVisible();
  await expect(firstLesson).toBeFocused();
  await expect(
    page.getByRole("heading", { name: "Разберёмся по шагам", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".example-walkthrough li")).toHaveCount(4);
  await expect(
    page.getByRole("heading", { name: "Проверим понимание", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("AI-наставник пока не подключён", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("#mentor-message")).toHaveCount(0);
  const planResponse = await page.request.get("/api/learning/plan");
  expect(planResponse.ok()).toBeTruthy();
  const plan = await planResponse.json();
  expect(plan.status).toBe("ready");
  expect(plan.learning_mode).toBe("starter");
  expect(plan.assessment_optional).toBe(true);
  expect(plan.assessment_run_id).toBeNull();
  expect(plan.skill_profile).toEqual([]);
  await capture(page, testInfo, "05-first-lesson", true);

  await page
    .getByRole("button", { name: "Перейти к вопросам", exact: false })
    .click();
  await expect(
    page.getByRole("heading", { name: "Проверим понимание", exact: true }),
  ).toBeVisible();
  const questions = page.locator(".knowledge-question");
  await expect(questions.first()).toBeVisible();
  // Deliberately choose without reading a server-side answer key. Feedback must
  // explain an answer whether this arbitrary choice succeeds or needs revision.
  for (const question of await questions.all())
    await question.getByRole("radio").first().check();
  await page
    .getByRole("button", { name: "Проверить ответы", exact: true })
    .click();
  await expect(page.locator(".check-feedback li").first()).toBeVisible();
  await capture(page, testInfo, "06-answer-feedback", true);
  await page
    .getByRole("button", { name: "Открыть практику", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Сейчас редактор кода не нужен",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".cm-editor")).toHaveCount(0);
  await expect(page.locator(".practice-instructions ol > li")).toHaveCount(3);
  await capture(page, testInfo, "07-guided-practice", true);

  await openWorkspace(
    page,
    testInfo,
    "/dashboard",
    new RegExp(`${name}, ваш следующий шаг`),
    "08-dashboard",
  );
  await expect(
    page.getByText("Начнём с самого начала.", { exact: false }),
  ).toBeVisible();
  if (testInfo.project.name === "mobile") {
    const menu = page.getByRole("button", {
      name: "Открыть меню",
      exact: true,
    });
    await expect(menu).toBeVisible();
    await menu.click();
    await expect(
      page.getByRole("button", { name: "Закрыть меню", exact: true }),
    ).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator(".app-sidebar")).toBeVisible();
    await capture(page, testInfo, "09-mobile-navigation", true);
    await page.keyboard.press("Escape");
    await expect(menu).toBeFocused();
    await expect(menu).toHaveAttribute("aria-expanded", "false");
  } else {
    await page.keyboard.press("Tab");
    const focused = await page.locator(":focus").evaluate((node) => {
      const style = getComputedStyle(node);
      return { outline: style.outlineStyle, shadow: style.boxShadow };
    });
    expect(
      focused.outline !== "none" || focused.shadow !== "none",
      "keyboard focus must remain visible",
    ).toBeTruthy();
  }
  await openWorkspace(
    page,
    testInfo,
    "/learning/path",
    "Ваш учебный путь",
    "10-course-path",
  );
  await expect(page.locator(".course-phase-card").first()).toContainText(
    "Основы Python",
  );
  await expect(page.locator(".course-phase-card").first()).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(
    page.getByRole("button", { name: "Все уроки", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Все уроки", exact: true }).click();
  const pathResponse = await page.request.get("/api/learning/path");
  expect(pathResponse.ok()).toBeTruthy();
  const coursePath = await pathResponse.json();
  expect(coursePath.total).toBeGreaterThan(0);
  await expect(page.locator(".course-path-item")).toHaveCount(coursePath.total);

  await openWorkspace(
    page,
    testInfo,
    "/account",
    "Аккаунт и настройки",
    "11-account",
  );
  await expect(
    page.getByRole("heading", { name: "Сессии входа", exact: true }),
  ).toBeVisible();
  await page.locator('input[name="display_name"]').fill(`${name} обновлён`);
  await page
    .getByRole("button", { name: "Сохранить настройки", exact: false })
    .click();
  await expect(
    page.getByText("Настройки обучения сохранены.", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator('input[name="display_name"]')).toHaveValue(
    `${name} обновлён`,
  );
  await page
    .getByRole("button", { name: "Сохранить уведомления", exact: true })
    .click();
  await expect(
    page.getByText("Предпочтения уведомлений сохранены.", { exact: true }),
  ).toBeVisible();
  await capture(page, testInfo, "12-account-saved", true);

  await openWorkspace(
    page,
    testInfo,
    "/jobs",
    "Чему учиться для вакансии",
    "13-career-empty",
  );
  await page
    .locator('input[name="title"]')
    .fill("Учебная вакансия Python Backend");
  await page
    .locator('textarea[name="text"]')
    .fill(
      "Требования: Python, SQL, PostgreSQL, FastAPI. Разработка HTTP API и тестирование с pytest.",
    );
  const vacancyResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/vacancies") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Разобрать требования", exact: true })
    .click();
  const vacancyCreated = await vacancyResponse;
  expect(vacancyCreated.ok()).toBeTruthy();
  const vacancy = await vacancyCreated.json();
  await expect(
    page.getByRole("heading", {
      name: "Учебная вакансия Python Backend",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Выбрать ориентиром обучения", exact: true })
    .click();
  await expect(
    page.getByText("Вакансия выбрана как ориентир обучения.", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".jobs-roadmap-list > li:visible")).toHaveCount(
    Math.min(6, vacancy.roadmap.length),
  );
  await expect(page.locator(".jobs-roadmap-list > li").first()).toContainText(
    "Переменные",
  );
  await expect(page.locator(".jobs-roadmap-list > li").nth(2)).toContainText(
    "Условия",
  );
  if (vacancy.roadmap.length > 6) {
    const remainingTopics = page.locator(".jobs-roadmap-disclosure > summary");
    await remainingTopics.click();
    await expect(page.locator(".jobs-roadmap-list > li:visible")).toHaveCount(
      vacancy.roadmap.length,
    );
    await remainingTopics.click();
  }
  await capture(page, testInfo, "14-career-result", true);

  await openWorkspace(
    page,
    testInfo,
    "/projects",
    "Ваши Backend-проекты",
    "15-projects-empty",
  );
  const createdResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/projects") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Создать проект", exact: false })
    .first()
    .click();
  const created = await createdResponse;
  expect(created.ok()).toBeTruthy();
  const project = await created.json();
  const requiredSections = project.milestones[0].required_sections;
  const artifact = requiredSections
    .map(
      (section) =>
        `## ${section}\nУчебный материал для одноразовой проверки интерфейса: описываем задачу, ограничения и ожидаемый результат.`,
    )
    .join("\n\n");
  await page.locator('textarea[name="artifact_text"]').first().fill(artifact);
  await page
    .getByRole("button", { name: "Отправить материал этапа", exact: true })
    .first()
    .click();
  await expect(
    page
      .locator(".project-submission-result")
      .first()
      .getByText("Материал принят", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(".project-submission-result")
      .first()
      .getByText("Код не выполнялся.", { exact: false }),
  ).toBeVisible();
  await capture(page, testInfo, "16-project-artifact", true);

  const portfolioForm = page.locator(".project-portfolio-section");
  const portfolioTitle = `Учебный проект ${testInfo.project.name}`;
  await portfolioForm.locator('input[name="title"]').fill(portfolioTitle);
  await portfolioForm
    .locator('textarea[name="summary"]')
    .fill(
      "Одноразовый проект браузерной проверки. Описание задачи и первого этапа обучения Python Backend.",
    );
  await portfolioForm.locator('input[name="published"]').check();
  await portfolioForm
    .getByRole("button", { name: "Сохранить портфолио", exact: true })
    .click();
  const publicLink = portfolioForm.getByRole("link", {
    name: "Посмотреть публичную страницу",
    exact: false,
  });
  await expect(publicLink).toBeVisible();
  const publicPath = await publicLink.getAttribute("href");
  expect(publicPath).toMatch(/^\/portfolio\//);
  await page.goto(publicPath);
  await expect(
    page.getByRole("heading", { level: 1, name: portfolioTitle, exact: true }),
  ).toBeVisible();
  await capture(page, testInfo, "23-public-portfolio");

  await openWorkspace(
    page,
    testInfo,
    "/billing",
    "Тариф и AI-наставник",
    "17-billing",
  );
  await expect(
    page
      .getByRole("button", { name: "Оплата пока недоступна", exact: true })
      .first(),
  ).toBeDisabled();
  await page.goto("/assessment");
  await expect(
    page.getByRole("heading", { name: "Начните с объяснений", exact: true }),
  ).toBeVisible();
  await capture(page, testInfo, "20-optional-diagnostic", true);
  await page
    .getByRole("button", {
      name: "Всё же попробовать диагностику",
      exact: true,
    })
    .click();
  await expect(page.locator(".assessment-question-title")).toBeVisible();
  await capture(page, testInfo, "21-diagnostic-question", true);
  await page
    .getByRole("button", { name: "Не знаю — пропустить", exact: true })
    .click();
  await expect(page.getByText("Вопрос 2", { exact: true })).toBeVisible();
  await capture(page, testInfo, "22-diagnostic-skip", true);
  await page.goto("/auth/reset");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await capture(page, testInfo, "18-password-recovery");
  await page.goto("/auth/verify");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await capture(page, testInfo, "19-email-verification");
  expect(
    pageErrors,
    "no browser runtime failures throughout the journey",
  ).toEqual([]);
});
