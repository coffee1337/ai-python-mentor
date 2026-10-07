import { test, expect } from "@playwright/test";

const PASSWORD = "Only-Disposable-CI-Account-2026";

async function headers(context) {
  const me = await context.request.get("/api/me");
  expect(me.status()).toBe(200);
  expect(me.headers()["cache-control"]).toBe("no-store");
  const user = await me.json();
  const csrf = (await context.cookies()).find((cookie) => cookie.name === "mentor_csrf");
  return { "X-CSRF-Token": decodeURIComponent(csrf.value), "X-Account-Scope": user.account_scope };
}

async function register(context, email) {
  const response = await context.request.post("/api/auth/register", { data: { email, password: PASSWORD } });
  expect(response.status()).toBe(201);
  const auth = await headers(context);
  const setup = await context.request.post("/api/onboarding", { headers: auth, data: {
    display_name: "Синхронизация", experience_level: "beginner", target_role: "Python Backend", weekly_minutes: 120,
  } });
  expect(setup.status()).toBe(200);
  return auth;
}

function draftUrl(identity) {
  return `/api/learning/drafts?${new URLSearchParams(Object.entries(identity).map(([key, value]) => [key, String(value)]))}`;
}

async function draft(context, identity, auth) {
  const response = await context.request.get(draftUrl(identity), { headers: auth });
  expect(response.status()).toBe(200);
  expect(response.headers()["cache-control"]).toBe("no-store");
  return response.json();
}

async function capture(page, testInfo, name) {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage: true });
  await page.screenshot({ path: testInfo.outputPath(`${name}-viewport.png`), fullPage: false });
  const dimensions = await page.evaluate(() => ({
    viewport: innerWidth, document: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport + 1);
}

test("two devices preserve drafts, conflicts and a paused study session", async ({ page, browser, baseURL }, testInfo) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const email = `browser-sync-${testInfo.project.name}-${Date.now()}@example.invalid`;
  const auth = await register(page.context(), email);
  const lessonResponse = await page.request.get("/api/learning/next");
  expect(lessonResponse.status()).toBe(200);
  const lesson = await lessonResponse.json();
  const flowIdentity = { kind: "lesson_flow", resource_id: lesson.id, version: Number(lesson.version), milestone_id: "" };
  await page.goto(`/learning?lesson=${encodeURIComponent(lesson.id)}`);
  await expect(page.getByRole("heading", { level: 1, name: lesson.title, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Перейти к вопросам", exact: false }).click();
  const radio = page.locator(".knowledge-question").first().getByRole("radio").first();
  await radio.check();
  const choice = await radio.inputValue();
  await expect.poll(async () => (await draft(page.context(), flowIdentity, auth)).content?.step).toBe(2);
  await expect.poll(async () => Object.values((await draft(page.context(), flowIdentity, auth)).content?.answers ?? {})).toContain(choice);

  const other = await browser.newContext({ baseURL, viewport: testInfo.project.use.viewport, reducedMotion: "reduce" });
  try {
    expect((await other.request.post("/api/auth/login", { data: { email, password: PASSWORD } })).status()).toBe(200);
    const otherAuth = await headers(other);
    const remote = await other.newPage();
    remote.on("pageerror", (error) => errors.push(error.message));
    await remote.goto(`/learning?lesson=${encodeURIComponent(lesson.id)}`);
    await expect(remote.getByRole("heading", { name: "Проверим понимание", exact: true })).toBeVisible();
    await expect(remote.locator(".knowledge-question").first().locator("input:checked")).toHaveValue(choice);
    await expect(remote.locator(".check-feedback")).toHaveCount(0);

    await page.getByRole("button", { name: "Открыть практику", exact: true }).click();
    await page.getByText("Объяснить своими словами · необязательно", { exact: true }).click();
    const explanation = "Мой неотправленный разбор: Python выполняет строки по порядку. 🐍";
    await page.locator("#reflection-text").fill(explanation);
    const reflectionIdentity = { ...flowIdentity, kind: "reflection" };
    await expect.poll(async () => (await draft(page.context(), reflectionIdentity, auth)).content?.text).toBe(explanation);
    await expect.poll(async () => (await draft(page.context(), flowIdentity, auth)).content?.step).toBe(3);
    await remote.reload();
    await remote.getByText("Объяснить своими словами · необязательно", { exact: true }).click();
    await expect(remote.locator("#reflection-text")).toHaveValue(explanation);

    const templates = await (await page.request.get("/api/projects/templates")).json();
    const created = await page.request.post("/api/projects", { headers: auth, data: { template_id: templates[0].id } });
    expect(created.status()).toBe(201);
    const project = await created.json();
    const identity = { kind: "project_milestone", resource_id: project.id, version: 0, milestone_id: project.milestones[0].id };
    const url = `/projects?project=${project.id}`;
    await page.goto(url);
    const editor = page.locator(`[id="artifact-${identity.milestone_id}"]`);
    const remoteEditor = remote.locator(`[id="artifact-${identity.milestone_id}"]`);
    const initial = "Первый приватный черновик этапа — café и 🐍.";
    await editor.fill(initial);
    await expect.poll(async () => (await draft(page.context(), identity, auth)).content?.artifact_text).toBe(initial);
    await remote.goto(url);
    await expect(remoteEditor).toHaveValue(initial);

    await page.route("**/api/learning/drafts", (route) => route.request().method() === "POST" ? route.abort() : route.continue());
    const local = "Мой вариант без сети: сохранить исходный текст.";
    await editor.fill(local);
    await expect(page.locator('.draft-sync-status[data-sync-phase="error"]')).toBeVisible();
    const account = "Второе устройство: уточнённое описание этапа.";
    await remoteEditor.fill(account);
    await expect.poll(async () => (await draft(other, identity, otherAuth)).content?.artifact_text).toBe(account);
    await page.unroute("**/api/learning/drafts");
    await page.getByRole("button", { name: "Повторить синхронизацию", exact: true }).click();
    await expect(page.locator(".draft-sync-conflict")).toBeVisible();
    await expect(editor).toHaveValue(local);
    await expect(page.locator(".draft-sync-conflict")).toContainText(account);
    await capture(page, testInfo, "30-cross-device-conflict");
    await page.getByRole("button", { name: "Использовать вариант из аккаунта", exact: true }).click();
    await expect(editor).toHaveValue(account);
    await page.getByText("Предыдущий вариант черновика на устройстве", { exact: true }).click();
    await page.getByRole("button", { name: "Вернуть предыдущий вариант", exact: true }).click();
    await expect(editor).toHaveValue(local);
    await expect.poll(async () => (await draft(page.context(), identity, auth)).content?.artifact_text).toBe(local);
    expect((await (await page.request.get(`/api/projects/${project.id}`)).json()).submissions).toEqual([]);
    await remote.close();

    await page.goto("/dashboard");
    await page.getByRole("button", { name: "Начать занятие", exact: true }).click();
    await expect(page.getByRole("button", { name: "Пауза", exact: true })).toBeVisible();
    const session = await (await page.request.get("/api/learning/study-session", { headers: auth })).json();
    const sessionId = session.session.id;
    await expect.poll(async () => (await (await page.request.get("/api/learning/study-session", { headers: auth })).json()).session.active_seconds).toBeGreaterThan(0);
    await page.getByRole("button", { name: "Пауза", exact: true }).click();
    await expect(page.getByRole("button", { name: "Продолжить занятие", exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Продолжить занятие", exact: true })).toBeVisible();
    const resumed = await other.newPage();
    await resumed.goto("/dashboard");
    await expect(resumed.getByRole("button", { name: "Продолжить занятие", exact: true })).toBeVisible();
    expect((await (await other.request.get("/api/learning/study-session", { headers: otherAuth })).json()).session.id).toBe(sessionId);
    await resumed.getByRole("button", { name: "Продолжить занятие", exact: true }).click();
    await expect(resumed.getByRole("button", { name: "Пауза", exact: true })).toBeVisible();
    await resumed.getByRole("link", { name: "История занятий →", exact: true }).click();
    await expect(resumed.getByRole("heading", { level: 1, name: "История занятий", exact: true })).toBeVisible();
    await resumed.getByRole("button", { name: "Завершить занятие", exact: true }).click();
    await expect(resumed.locator(".study-session-history-list > li").first()).toContainText("Занятие завершено");
    expect((await (await other.request.get("/api/learning/study-session", { headers: otherAuth })).json()).session).toBeNull();
    await resumed.getByRole("button", { name: "Начать занятие", exact: true }).click();
    await resumed.getByRole("button", { name: "Отменить занятие", exact: true }).click();
    await resumed.getByRole("button", { name: "Подтвердить отмену", exact: true }).click();
    await expect(resumed.locator(".study-session-history-list > li").first()).toContainText("Занятие отменено");
    await resumed.getByLabel("Показать", { exact: true }).selectOption("50");
    await expect(resumed.locator(".study-session-history-list > li")).toHaveCount(2);
    await capture(resumed, testInfo, "31-study-session-history");
    expect(errors).toEqual([]);
  } finally {
    await other.close();
  }
});

test("a stale tab never copies its private draft into a different account", async ({ page }, testInfo) => {
  const firstAuth = await register(page.context(), `browser-account-a-${testInfo.project.name}-${Date.now()}@example.invalid`);
  const lesson = await (await page.request.get("/api/learning/next")).json();
  const identity = { kind: "reflection", resource_id: lesson.id, version: Number(lesson.version), milestone_id: "" };
  await page.goto(`/learning?lesson=${encodeURIComponent(lesson.id)}`);
  await page.getByRole("button", { name: "Попрактиковаться", exact: false }).click();
  await page.getByText("Объяснить своими словами · необязательно", { exact: true }).click();
  const privateText = "Этот неотправленный текст принадлежит первому аккаунту.";
  await page.locator("#reflection-text").fill(privateText);
  await expect.poll(async () => (await draft(page.context(), identity, firstAuth)).content?.text).toBe(privateText);

  // API login/registration changes the shared cookies without a frontend event,
  // exercising the server precondition even if cross-tab broadcast is missed.
  const secondAuth = await register(page.context(), `browser-account-b-${testInfo.project.name}-${Date.now()}@example.invalid`);
  const secondTab = await page.context().newPage();
  try {
    await secondTab.goto(`/learning?lesson=${encodeURIComponent(lesson.id)}`);
    await expect(secondTab.getByRole("heading", { level: 1, name: lesson.title, exact: true })).toBeVisible();
    const lateWrites = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().endsWith("/api/learning/drafts")) lateWrites.push(request.postData());
    });
    await page.bringToFront();
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(page).toHaveURL(/\/auth$/);
    const secondDraft = await draft(page.context(), identity, secondAuth);
    expect(secondDraft.revision).toBe(0);
    expect(secondDraft.content).toBeNull();
    expect(lateWrites.some((body) => body?.includes(privateText))).toBe(false);
    const rejected = await page.request.post("/api/learning/drafts", { headers: {
      ...secondAuth, "X-Account-Scope": firstAuth["X-Account-Scope"],
    }, data: { identity, expected_revision: 0, content: { text: privateText } } });
    expect(rejected.status()).toBe(409);
    expect((await rejected.json()).detail.code).toBe("account_changed");
    expect((await draft(page.context(), identity, secondAuth)).content).toBeNull();
  } finally {
    await secondTab.close();
  }
});
