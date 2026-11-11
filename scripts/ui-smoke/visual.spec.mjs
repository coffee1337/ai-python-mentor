// Visual audit at the three widths the product must support: 360, 768, 1440.
//
// It fails on horizontal overflow, on a missing heading and on a page that
// renders no content, and it stores a full-page screenshot per page and width
// so a human can review the result instead of trusting a green check.
import { expect, test } from "@playwright/test";

const WIDTHS = [
  { name: "360", width: 360, height: 800 },
  { name: "768", width: 768, height: 1024 },
  { name: "1440", width: 1440, height: 900 },
];

const PAGES = [
  { path: "/dashboard", heading: /На сегодня|С возвращением|Продолжить/ },
  { path: "/learning?lesson=variables-v1", heading: /./ },
  { path: "/learning/path", heading: /./ },
  { path: "/learning/progress", heading: /./ },
  { path: "/learning/reviews", heading: /./ },
  { path: "/projects", heading: /./ },
  { path: "/account", heading: /./ },
  { path: "/billing", heading: /./ },
];

test.describe("visual audit", () => {
  for (const width of WIDTHS) {
    test(`every page fits ${width.name}px without horizontal overflow`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width: width.width, height: width.height });
      await page.goto("/auth");
      await page.getByRole("button", { name: "Вход", exact: true }).click();
      await page.getByLabel("Email", { exact: true }).fill(`browser-recovery-${testInfo.project.name}@example.invalid`);
      await page.getByLabel("Пароль", { exact: true }).fill("Only-Disposable-CI-Account-2026");
      await page.getByRole("button", { name: "Войти", exact: true }).click();
      await expect(page).toHaveURL(/\/dashboard$/);

      for (const target of PAGES) {
        await page.goto(target.path);
        await expect(page.locator("h1").first()).toBeVisible();
        await page.evaluate(() => document.fonts.ready);
        const overflow = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));
        expect(overflow.scrollWidth, `${target.path} @${width.name}px overflows horizontally`)
          .toBeLessThanOrEqual(overflow.clientWidth + 1);
        const slug = target.path.replace(/[/?=]/g, "-").replace(/^-|-$/g, "");
        await page.screenshot({ path: testInfo.outputPath(`${width.name}-${slug}.png`), fullPage: true });
      }
    });
  }
});
