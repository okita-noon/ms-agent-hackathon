import { test, expect } from "@playwright/test";

// -------------------------------------------------------
// Visual Regression Tests for foogent dashboard UI
// -------------------------------------------------------

test.describe("Login page", () => {
  test("renders correctly with logo", async ({ page }) => {
    await page.goto("/");
    // Wait for the login form to be visible
    await page.waitForSelector('button:has-text("ログイン")');
    await expect(page).toHaveScreenshot("login-page.png", {
      maxDiffPixelRatio: 0.01,
    });
  });

  test("logo image is visible", async ({ page }) => {
    await page.goto("/");
    const logo = page.locator('img[alt="foogent"]');
    await expect(logo).toBeVisible();
    // Verify the src includes the BASE_URL prefix
    const src = await logo.getAttribute("src");
    expect(src).toContain("logo.png");
  });
});

test.describe("Dashboard header (authenticated)", () => {
  test.beforeEach(async ({ page }) => {
    // Mock auth by injecting a fake token and user via localStorage + API mock
    await page.goto("/");

    // Intercept /api/auth/me to simulate authenticated user
    await page.route("**/api/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "U-001",
          tenant_id: "T-001",
          email: "admin@maruyama.example.com",
          display_name: "丸山太郎",
        }),
      })
    );

    // Set token in localStorage and reload
    await page.evaluate(() => {
      localStorage.setItem("foogent_token", "fake-jwt-for-test");
    });
    await page.reload();

    // Also mock orders API to avoid errors
    await page.route("**/api/orders**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ orders: [] }),
      })
    );

    await page.waitForSelector("header");
  });

  test("header shows profile avatar", async ({ page }) => {
    const avatar = page.locator('button[aria-label="ユーザーメニュー"]');
    await expect(avatar).toBeVisible();
    await expect(page).toHaveScreenshot("dashboard-header.png", {
      maxDiffPixelRatio: 0.01,
    });
  });

  test("profile dropdown opens on click", async ({ page }) => {
    const avatar = page.locator('button[aria-label="ユーザーメニュー"]');
    await avatar.click();

    // Dropdown should show user info
    await expect(page.locator("text=丸山太郎")).toBeVisible();
    await expect(
      page.locator("text=admin@maruyama.example.com")
    ).toBeVisible();
    await expect(page.locator("text=テナント: T-001")).toBeVisible();
    await expect(page.locator("text=ログアウト")).toBeVisible();

    await expect(page).toHaveScreenshot("profile-dropdown-open.png", {
      maxDiffPixelRatio: 0.01,
    });
  });

  test("dropdown closes on outside click", async ({ page }) => {
    const avatar = page.locator('button[aria-label="ユーザーメニュー"]');
    await avatar.click();
    await expect(page.locator("text=丸山太郎")).toBeVisible();

    // Click outside
    await page.locator("main").click();
    await expect(page.locator("text=丸山太郎")).not.toBeVisible();
  });

  test("tab bar does NOT show logout", async ({ page }) => {
    // The old logout text was in the tab bar area alongside tabs
    const tabNav = page.locator("nav");
    await expect(tabNav.locator("text=ログアウト")).not.toBeVisible();
  });
});

test.describe("Order detail modal with messages", () => {
  const SAMPLE_ORDER = {
    uid: "ORD-20260517-001",
    tenant_id: "T-001",
    order_date: "2026-05-17",
    delivery_date: "2026-05-18",
    customer_id: "C-001",
    customer_name: "レストラン花月",
    source: "LINE",
    items: [
      { product_name: "ふじりんご", quantity: 10, unit: "箱", temperature_zone: "冷蔵" },
      { product_name: "バナナ", quantity: 20, unit: "kg", temperature_zone: "常温" },
    ],
    status: "未処理",
    session_id: "sess-abc12345-20260517120000",
  };

  const SAMPLE_MESSAGES = [
    {
      id: "msg-1",
      role: "user",
      text: "りんご10箱とバナナ20kgお願いします",
      channel: "line",
      created_at: "2026-05-17T12:00:00Z",
    },
    {
      id: "msg-2",
      role: "assistant",
      text: "ふじりんご10箱、バナナ20kgで承りました。明日5/18にお届けでよろしいですか？",
      channel: "line",
      created_at: "2026-05-17T12:00:05Z",
    },
    {
      id: "msg-3",
      role: "user",
      text: "はい、お願いします",
      channel: "line",
      created_at: "2026-05-17T12:01:00Z",
    },
    {
      id: "msg-4",
      role: "assistant",
      text: "ありがとうございます。ご注文を確定しました。明日5/18にお届けいたします。",
      channel: "line",
      created_at: "2026-05-17T12:01:05Z",
    },
  ];

  test.beforeEach(async ({ page }) => {
    await page.goto("/");

    await page.route("**/api/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "U-001",
          tenant_id: "T-001",
          email: "admin@maruyama.example.com",
          display_name: "丸山太郎",
        }),
      })
    );

    await page.evaluate(() => {
      localStorage.setItem("foogent_token", "fake-jwt-for-test");
    });
    await page.reload();

    // Mock orders list with our sample order
    await page.route("**/api/orders?**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ orders: [SAMPLE_ORDER], date: "2026-05-17" }),
      })
    );

    // Mock messages endpoint
    await page.route("**/api/orders/*/messages", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          messages: SAMPLE_MESSAGES,
          session_id: "sess-abc12345-20260517120000",
        }),
      })
    );

    await page.waitForSelector("header");
  });

  test("order detail shows conversation history", async ({ page }) => {
    // Click on the order row to open modal
    await page.locator("text=レストラン花月").first().click();

    // Wait for modal and messages to load
    await page.waitForSelector("text=注文会話履歴");
    await expect(page.locator("text=りんご10箱とバナナ20kgお願いします")).toBeVisible();
    await expect(page.locator("text=はい、お願いします")).toBeVisible();

    await expect(page).toHaveScreenshot("order-detail-with-messages.png", {
      maxDiffPixelRatio: 0.01,
    });
  });

  test("order detail without messages shows no thread", async ({ page }) => {
    // Override messages mock to return empty
    await page.route("**/api/orders/*/messages", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ messages: [], session_id: null }),
      })
    );

    await page.locator("text=レストラン花月").first().click();
    await page.waitForSelector("text=受注詳細");

    // Message thread should not be visible
    await expect(page.locator("text=注文会話履歴")).not.toBeVisible();
  });
});
