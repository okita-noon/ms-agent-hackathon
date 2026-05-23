import { test } from "@playwright/test";

test("capture order table screenshot", async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: "test-user",
        tenant_id: "T-001",
        email: "test@example.com",
        display_name: "テストユーザー",
      }),
    }),
  );
  await page.route("**/api/orders**", (route) =>
    route.fulfill({ status: 500, body: "error" }),
  );
  await page.route("**/api/agent/features", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ dashboard_agent: false }),
    }),
  );

  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  await page.evaluate(() => localStorage.setItem("foogent_token", "test-token"));
  await page.goto("/");
  await page.waitForSelector("text=注文一覧", { timeout: 15_000 });

  // Scroll to order table section
  await page.locator("text=注文一覧").first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);

  await page.screenshot({ path: "test-results/order-table.png", fullPage: true });
});
