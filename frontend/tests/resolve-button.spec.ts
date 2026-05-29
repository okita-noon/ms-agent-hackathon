import { test, expect } from "@playwright/test";

/**
 * 対応済みボタンのスクリーンショット用テスト。
 * フロントエンドのモックだけで描画を再現し、ExceptionModal と
 * 受注詳細モーダルの両方に「対応済みにする」2タップ式ボタンが出ることを確認する。
 */

const fakeUser = {
  user_id: "test-user",
  tenant_id: "T-001",
  email: "test@example.com",
  display_name: "テストユーザー",
};

const today = "2026-05-28";

const fakeOrder = {
  uid: "ORD-DEMO-RESOLVE",
  id: "ORD-DEMO-RESOLVE",
  tenant_id: "T-001",
  order_date: today,
  delivery_date: today,
  preparation_date: today,
  customer_id: "C-001",
  customer_name: "ビストロ青葉",
  source: "LINE",
  items: [
    {
      product_id: "P-001",
      product_name: "りんご",
      quantity: 5,
      unit: "箱",
      temperature_zone: "冷蔵",
    },
  ],
  status: "要対応",
  remarks: null,
  memo: null,
  session_id: null,
  created_at: `${today}T09:00:00+09:00`,
  updated_at: `${today}T09:00:00+09:00`,
};

const fakeException = {
  id: "exc-ORD-DEMO-RESOLVE-needs_review",
  order_id: "ORD-DEMO-RESOLVE",
  customer_id: "C-001",
  customer_name: "ビストロ青葉",
  type: "needs_review",
  severity: "high",
  title: "担当者確認が必要な受注",
  summary: "AIが自動処理できず「要対応」となっています。",
  suggested_action: "注文内容と会話履歴を確認し、必要なら顧客へ問い合わせてください。",
  evidence: [{ label: "ステータス", value: "要対応" }],
  metadata: {},
};

async function mockBackend(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fakeUser),
    }),
  );
  await page.route("**/api/orders?**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        orders: [fakeOrder],
        total: 1,
        limit: 50,
        offset: 0,
        filters: { status: null, source: null, q: null },
      }),
    }),
  );
  await page.route("**/api/customers**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ customers: [] }) }),
  );
  await page.route("**/api/products**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ products: [] }) }),
  );
  await page.route("**/api/inventory**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ inventory: [] }) }),
  );
  await page.route("**/api/agent/features", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        dashboard_agent: true,
        exception_triage: true,
        resolution_agent: true,
        resolution_execute: false,
        demo_mode: false,
      }),
    }),
  );
  await page.route("**/api/agent/exceptions**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        enabled: true,
        date: today,
        date_field: "delivery_date",
        filters: { status: null, source: null, q: null, limit: 50, offset: 0 },
        cases: [fakeException],
      }),
    }),
  );
  await page.route("**/api/orders/events", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: ":\n\n",
    }),
  );
  await page.route("**/api/orders/*/messages**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ messages: [], session_id: null }),
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
  await page.setViewportSize({ width: 1400, height: 900 });
});

test("exception modal shows '対応済みにする' button for needs_review case", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector("text=受注一覧", { timeout: 15_000 });
  // DashboardAgentPanel exposes a "詳細を確認" button to open the exception modal
  await page.locator("button:has-text('詳細を確認')").first().click();
  await page.waitForSelector("text=対応済みにする", { timeout: 5_000 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: "test-results/resolve-01-exception-modal.png", fullPage: false });

  // Click once to enter confirm state
  await page.locator("button:has-text('対応済みにする')").click();
  await page.waitForSelector("text=もう一度押して確定", { timeout: 2_000 });
  await page.screenshot({ path: "test-results/resolve-02-exception-modal-confirm.png", fullPage: false });
});

test("order detail modal shows '対応済みにする' button when status=要対応", async ({ page }) => {
  await page.goto("/");
  await page.waitForSelector("text=受注一覧", { timeout: 15_000 });
  await page.locator("tr").nth(1).click();
  await page.waitForSelector("text=受注詳細", { timeout: 5_000 });
  await page.waitForSelector("text=対応済みにする", { timeout: 5_000 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: "test-results/resolve-03-order-detail.png", fullPage: false });

  await page.locator("button:has-text('対応済みにする')").click();
  await page.waitForSelector("text=もう一度押して確定", { timeout: 2_000 });
  await page.screenshot({ path: "test-results/resolve-04-order-detail-confirm.png", fullPage: false });
});
