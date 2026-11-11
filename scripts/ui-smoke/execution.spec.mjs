// End-to-end proof that learner code is executed by the isolated runner.
//
// Requires the whole execution chain to be up: API with RUNNER_* and
// EXECUTION_JOBS_ENABLED=true, the durable worker (python -m app.jobs) and the
// runner worker with its mTLS certificate. The test is skipped unless
// EXECUTION_E2E=1, because a plain UI run has no runner.
import { expect, test } from "@playwright/test";

const SOLUTION = `def double(value):
    return value * 2


def solve(payload):
    return [double(value) for value in payload["values"]]
`;

const SKIP = process.env.EXECUTION_E2E !== "1";

test.describe("code execution", () => {
  test.skip(SKIP, "EXECUTION_E2E=1 is required: the runner and the execution worker must be running");

  test("learner solution runs in the isolated runner and grades to 3 of 3", async ({ page }, testInfo) => {
    await page.goto("/auth");
    await page.getByRole("button", { name: "Вход", exact: true }).click();
    await page.getByLabel("Email", { exact: true }).fill(`browser-recovery-${testInfo.project.name}@example.invalid`);
    await page.getByLabel("Пароль", { exact: true }).fill("Only-Disposable-CI-Account-2026");
    await page.getByRole("button", { name: "Войти", exact: true }).click();
    await expect(page).toHaveURL(/\/dashboard$/);

    await page.goto("/learning?lesson=functions-v1");
    await page.getByRole("button", { name: "Попрактиковаться", exact: false }).click();
    await page.getByText("Тренировка с кодом · отдельное задание", { exact: true }).click();

    const editor = page.locator(".cm-content");
    await expect(editor).toBeVisible();
    await editor.fill(SOLUTION);

    const submit = page.getByRole("button", { name: "Отправить на проверку", exact: true });
    await expect(submit).toBeEnabled();
    await submit.click();

    // The job is queued, picked up by the worker, executed in the sandbox and
    // polled back into the page; 60 s covers worker latency and one retry.
    await expect(page.getByText(/Тесты: \d+ из \d+/).first()).toBeVisible({ timeout: 60_000 });
    const result = await page.getByText(/Тесты: \d+ из \d+/).first().innerText();
    expect(result).toMatch(/Тесты: (\d+) из \1/);
    await expect(page.getByText("Обработка завершена", { exact: true })).toBeVisible();

    await page.screenshot({ path: testInfo.outputPath("execution-result.png"), fullPage: true });
  });
});
