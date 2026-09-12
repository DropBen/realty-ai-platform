import { expect, test, type BrowserContext, type Page } from "@playwright/test";

// A dedicated demo identity keeps independent journeys inside the unchanged user rate limit.
let cookies: Awaited<ReturnType<BrowserContext["cookies"]>> | undefined;
async function signIn(page: Page) {
  if (!cookies) {
    const registered = await page.request.post("/api/v1/auth/register", {
      data: {
        name: "Reviewer",
        email: `review-${Date.now()}@example.com`,
        password: "Browser-fixture-password-123!",
        organization: "Review regression workspace",
      },
    });
    expect(registered.status()).toBe(201);
    const account = await registered.json();
    const contact = await page.request.post("/api/v1/crm/contacts", {
      headers: { "X-CSRF-Token": account.csrf_token },
      data: {
        name: "Review Buyer",
        email: "review-buyer@example.com",
        kind: "buyer",
      },
    });
    expect(contact.status()).toBe(201);
    cookies = await page.context().cookies();
  } else {
    await page.context().addCookies(cookies);
  }
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: /Good (morning|afternoon|evening), Reviewer/,
    }),
  ).toBeVisible();
}

async function reviewFixture(page: Page, kind: "create_task" | "send_email") {
  return page.evaluate(async (kind) => {
    const csrf = decodeURIComponent(
      document.cookie
        .split("; ")
        .find((v) => v.startsWith("realty_csrf="))!
        .split("=")[1],
    );
    const contacts = await fetch("/api/v1/crm/contacts?kind=buyer").then((r) =>
      r.json(),
    );
    const contact = contacts.items.find(
      (item: { email: string }) => item.email,
    );
    const title = "Review boundary " + Date.now();
    const response = await fetch("/api/v1/actions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({
        kind,
        title,
        reason: "Browser review regression",
        contact_id: contact.id,
        payload:
          kind === "send_email"
            ? {
                to: contact.email,
                subject: "Original subject",
                body: "Original draft",
              }
            : { title, contact_id: contact.id },
      }),
    });
    if (!response.ok) throw new Error("Could not create review fixture");
    return response.json();
  }, kind);
}

test("scheduled approval can be withdrawn before execution", async ({
  page,
}) => {
  await signIn(page);
  const action = await reviewFixture(page, "create_task");
  await page.goto("/actions");
  await page
    .locator(".action-card")
    .filter({ hasText: action.title })
    .getByRole("button", { name: "Review suggestion" })
    .click();
  const future = new Date(Date.now() + 3600000);
  const local = new Date(future.getTime() - future.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
  await page.getByLabel("Execute at (optional)").fill(local);
  await page.getByRole("button", { name: "Approve action" }).click();
  await page.getByRole("button", { name: "Queued", exact: true }).click();
  await page
    .locator(".action-card")
    .filter({ hasText: action.title })
    .getByRole("button", { name: "View details" })
    .click();
  await page.getByRole("button", { name: "Withdraw approval" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const state = await page.evaluate(async (id) => {
    const data = await fetch("/api/v1/actions").then((r) => r.json());
    return data.items.find((item: { id: string }) => item.id === id);
  }, action.id);
  expect(state.status).toBe("rejected");
  expect(state.approved_hash).toBeNull();
});

test("email review uses labelled fields and requires fresh approval after editing", async ({
  page,
}) => {
  await signIn(page);
  const action = await reviewFixture(page, "send_email");
  await page.goto("/actions");
  const card = page.locator(".action-card").filter({ hasText: action.title });
  await card.getByRole("button", { name: "Review suggestion" }).click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await expect(page.getByLabel("Recipient", { exact: true })).toHaveAttribute(
    "readonly",
  );
  await page.getByLabel("Subject", { exact: true }).fill("Reviewed subject");
  await page
    .getByLabel("Message", { exact: true })
    .fill("Thank you. I will call at the agreed time.");
  const { default: AxeBuilder } = await import("@axe-core/playwright");
  const accessibility = await new AxeBuilder({ page })
    .include("dialog[open]")
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await card.getByRole("button", { name: "Review suggestion" }).click();
  await expect(
    page.getByText("Reviewed subject", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Thank you. I will call at the agreed time.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve action" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Reject", exact: true }).click();
});

test("action list recovers from an upstream HTML error", async ({ page }) => {
  await signIn(page);
  const endpoint = /\/api\/v1\/actions\?/;
  await page.route(endpoint, (route) =>
    route.fulfill({
      status: 503,
      contentType: "text/html",
      body: "<html>Internal proxy diagnostics must not appear</html>",
    }),
  );
  await page.goto("/actions");
  await expect(
    page.getByRole("alert").filter({ hasText: "We couldn't load this" }),
  ).toBeVisible();
  await expect(
    page.getByText("Internal proxy diagnostics must not appear"),
  ).toHaveCount(0);
  await page.unroute(endpoint);
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "We couldn't load this" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Your action center" }),
  ).toBeVisible();
});
