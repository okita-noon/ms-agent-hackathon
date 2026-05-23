import { test } from "@playwright/test";

const fakeUser = {
  user_id: "test-user",
  tenant_id: "T-001",
  email: "test@example.com",
  display_name: "テストユーザー",
};

async function mockBackend(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fakeUser),
    }),
  );
  await page.route("**/api/orders**", (route) =>
    route.fulfill({ status: 500, body: "error" }),
  );
  await page.route("**/api/customers**", (route) =>
    route.fulfill({ status: 500, body: "error" }),
  );
  await page.route("**/api/agent/features", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ dashboard_agent: false }),
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  await page.evaluate(() => localStorage.setItem("foogent_token", "test-token"));
});

test("orders page is default (issue 63 & 64)", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector("text=注文一覧", { timeout: 15_000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: "test-results/01-orders-default.png", fullPage: true });
});

test("analytics tab shows stats and charts (issue 63)", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector("text=注文一覧", { timeout: 15_000 });
  await page.click("text=分析");
  await page.waitForSelector("text=ステータス別", { timeout: 5_000 });
  await page.waitForTimeout(700);
  await page.screenshot({ path: "test-results/02-analytics-tab.png", fullPage: true });
});

test("customers shows delivery lead time (issue 65)", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector("text=注文一覧", { timeout: 15_000 });
  await page.click("text=顧客");
  await page.waitForSelector("text=納品グループ", { timeout: 5_000 });
  await page.waitForTimeout(500);
  await page.screenshot({ path: "test-results/03-customers.png", fullPage: true });
});

test("customer edit modal exposes lead time (issue 65)", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector("text=注文一覧", { timeout: 15_000 });
  await page.click("text=顧客");
  await page.waitForSelector("text=納品グループ", { timeout: 5_000 });
  await page.locator("button:has-text('編集')").first().click();
  await page.waitForSelector("text=顧客編集", { timeout: 5_000 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: "test-results/04-customer-edit.png", fullPage: true });
});

test("order detail with memo editor (issue 69)", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector("text=注文一覧", { timeout: 15_000 });
  // Open the first row in the demo data
  await page.locator("tr").nth(1).click();
  await page.waitForSelector("text=受注詳細", { timeout: 5_000 });
  await page.waitForSelector("text=メモ（アレルギー対応・特別包装など）", { timeout: 5_000 });
  await page.waitForTimeout(400);
  await page.screenshot({ path: "test-results/05-order-detail-memo.png", fullPage: true });
});
