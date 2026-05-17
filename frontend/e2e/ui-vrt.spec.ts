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
