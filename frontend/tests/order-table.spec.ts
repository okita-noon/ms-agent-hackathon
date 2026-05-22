import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  // Mock /api/auth/me so the app treats us as logged in
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

  // Mock /api/orders to return empty (so demo fallback kicks in)
  await page.route("**/api/orders**", (route) =>
    route.fulfill({ status: 500, body: "error" }),
  );

  // Mock agent features to return disabled
  await page.route("**/api/agent/features", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ dashboard_agent: false }),
    }),
  );

  await page.goto("/dashboard/");
  await page.evaluate(() => localStorage.setItem("foogent_token", "test-token"));
  await page.goto("/dashboard/");
  await page.waitForSelector("text=注文一覧", { timeout: 15_000 });
});

test("section header shows title and subtitle", async ({ page }) => {
  const header = page.locator("h2", { hasText: "注文一覧" });
  await expect(header).toBeVisible();
  await expect(page.locator("text=すべての注文の確認・管理ができます")).toBeVisible();
});

test("stat badges show accepted and review counts", async ({ page }) => {
  const acceptedBadge = page.locator("span").filter({ hasText: /受注\s+\d+件/ }).first();
  await expect(acceptedBadge).toBeVisible();
  const reviewBadge = page.locator("span").filter({ hasText: /要対応\s+\d+件/ }).first();
  await expect(reviewBadge).toBeVisible();
});

test("filter bar elements are present", async ({ page }) => {
  await expect(page.getByPlaceholder("注文ID・商品・顧客名で検索")).toBeVisible();
  await expect(page.locator("label", { hasText: "ステータス" })).toBeVisible();
  await expect(page.locator("label", { hasText: "チャネル" })).toBeVisible();
  await expect(page.locator("label", { hasText: "温度帯" })).toBeVisible();
  await expect(page.locator("label", { hasText: "並び順" })).toBeVisible();
  await expect(page.locator("button", { hasText: "絞り込み" })).toBeVisible();
});

test("table has 7 correct column headers", async ({ page }) => {
  const headers = page.locator("thead th");
  await expect(headers).toHaveCount(7);
  await expect(headers.nth(0)).toContainText("受注日時");
  await expect(headers.nth(1)).toContainText("顧客名");
  await expect(headers.nth(2)).toContainText("チャネル");
  await expect(headers.nth(3)).toContainText("商品（温度帯）");
  await expect(headers.nth(4)).toContainText("ステータス");
  await expect(headers.nth(5)).toContainText("配送情報（予定）");
  await expect(headers.nth(6)).toContainText("備考");
});

test("channel is rendered as a badge with icon", async ({ page }) => {
  const channelCell = page.locator("tbody tr").first().locator("td").nth(2);
  const badge = channelCell.locator("span").first();
  await expect(badge).toBeVisible();
  await expect(badge.locator("svg")).toBeVisible();
});

test("customer name cell has avatar icon", async ({ page }) => {
  const customerCell = page.locator("tbody tr").first().locator("td").nth(1);
  const avatar = customerCell.locator("div.rounded-full");
  await expect(avatar).toBeVisible();
  await expect(avatar.locator("svg")).toBeVisible();
});

test("product cell shows temperature badge", async ({ page }) => {
  const productCell = page.locator("tbody tr").first().locator("td").nth(3);
  const tempBadge = productCell.locator("span").filter({ hasText: /冷凍|冷蔵|常温/ }).first();
  await expect(tempBadge).toBeVisible();
});

test("delivery cell shows clock icon with time slot", async ({ page }) => {
  const rows = page.locator("tbody tr");
  const count = await rows.count();
  let found = false;
  for (let i = 0; i < count; i++) {
    const deliveryCell = rows.nth(i).locator("td").nth(5);
    const clock = deliveryCell.locator("svg");
    if ((await clock.count()) > 0) {
      await expect(clock.first()).toBeVisible();
      found = true;
      break;
    }
  }
  expect(found).toBe(true);
});

test("row has chevron at the end", async ({ page }) => {
  const remarksCell = page.locator("tbody tr").first().locator("td").nth(6);
  const chevron = remarksCell.locator("svg");
  await expect(chevron).toBeVisible();
});

test("pagination is visible", async ({ page }) => {
  await expect(page.locator("text=件を表示")).toBeVisible();
  await expect(page.locator("text=表示件数")).toBeVisible();
});

test("search filter works", async ({ page }) => {
  const searchInput = page.getByPlaceholder("注文ID・商品・顧客名で検索");
  const rowsBefore = await page.locator("tbody tr").count();
  expect(rowsBefore).toBeGreaterThan(0);

  await searchInput.fill("メロン");
  // Demo filter re-renders after fetch attempt
  await page.waitForTimeout(1500);
  const rowsAfter = await page.locator("tbody tr").count();
  expect(rowsAfter).toBeLessThanOrEqual(rowsBefore);
  expect(rowsAfter).toBeGreaterThan(0);
});

test("row click opens detail modal", async ({ page }) => {
  await page.locator("tbody tr").first().click();
  await expect(page.locator("text=受注詳細").first()).toBeVisible({ timeout: 5000 });
});
