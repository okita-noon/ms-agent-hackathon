import { test, expect } from "@playwright/test";

const DEPLOYED_BASE = "https://storderaidev2.z11.web.core.windows.net";

test.describe("SSO Login flow (deployed)", () => {
  test.skip(
    !process.env.TEST_DEPLOYED,
    "Set TEST_DEPLOYED=1 to run against the live site"
  );

  test("login page renders with Microsoft SSO button", async ({ page }) => {
    await page.goto(`${DEPLOYED_BASE}/login`);
    await expect(
      page.locator("text=Microsoft アカウントでログイン")
    ).toBeVisible();
  });

  test("SSO button opens Microsoft login popup", async ({ page, context }) => {
    await page.goto(`${DEPLOYED_BASE}/login`);

    const popupPromise = context.waitForEvent("page", { timeout: 15_000 });
    await page.click("text=Microsoft アカウントでログイン");
    const popup = await popupPromise;

    await popup.waitForLoadState("domcontentloaded");
    const popupUrl = popup.url();

    expect(popupUrl).toContain("login.microsoftonline.com");
    expect(popupUrl).not.toContain("/login");

    await popup.close();
  });

  test("popup redirectUri does not reference auth-popup.html", async ({
    page,
    context,
  }) => {
    await page.goto(`${DEPLOYED_BASE}/login`);

    const popupPromise = context.waitForEvent("page", { timeout: 15_000 });
    await page.click("text=Microsoft アカウントでログイン");
    const popup = await popupPromise;

    await popup.waitForLoadState("domcontentloaded");
    const popupUrl = popup.url();

    if (popupUrl.includes("login.microsoftonline.com")) {
      const url = new URL(popupUrl);
      const redirectUri = url.searchParams.get("redirect_uri") || "";
      expect(redirectUri).not.toContain("auth-popup.html");
      expect(redirectUri).not.toContain("/dashboard");
    }

    await popup.close();
  });

  test("popup does not render React app", async ({ context }) => {
    const popup = await context.newPage();

    await popup.addInitScript(() => {
      Object.defineProperty(window, "opener", {
        value: { closed: false },
        writable: false,
      });
    });

    await popup.goto(`${DEPLOYED_BASE}/`, { waitUntil: "domcontentloaded" });

    const reactRoot = popup.locator("#root");
    await expect(reactRoot).toBeEmpty({ timeout: 5_000 });
    await expect(popup).toHaveTitle("サインイン中…");

    await popup.close();
  });
});

test.describe("SSO Login flow (local dev)", () => {
  test("login page loads without infinite loading", async ({ page }) => {
    await page.goto("/login");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("text=ログイン").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.locator("text=foogentを起動しています")
    ).not.toBeVisible();
  });

  test("login page has Microsoft SSO button", async ({ page }) => {
    await page.goto("/login");
    await expect(
      page.locator("text=Microsoft アカウントでログイン")
    ).toBeVisible();
  });

  test("popup window does not render React app", async ({ context }) => {
    const popup = await context.newPage();

    await popup.addInitScript(() => {
      Object.defineProperty(window, "opener", {
        value: { closed: false },
        writable: false,
      });
    });

    await popup.goto("/", { waitUntil: "domcontentloaded" });

    const reactRoot = popup.locator("#root");
    await expect(reactRoot).toBeEmpty({ timeout: 5_000 });
    await expect(popup).toHaveTitle("サインイン中…");

    await popup.close();
  });
});
