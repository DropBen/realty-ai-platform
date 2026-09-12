import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore demo workspace" }).click();
  await expect(
    page.getByRole("heading", {
      name: /Good (morning|afternoon|evening), Sarah/,
    }),
  ).toBeVisible();
}

test("demo dashboard, navigation and mobile fit", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await signIn(page);
  await expect(
    page.getByText(
      "Demo workspace · Fictional data. External sending is disabled.",
    ),
  ).toBeVisible();
  await expect(page.getByText("Your next best moves")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: `test-results/dashboard-${testInfo.project.name}.png`,
    fullPage: true,
  });
  for (const path of [
    "/contacts",
    "/buyers",
    "/sellers",
    "/leads",
    "/properties",
    "/deals",
    "/calendar",
    "/tasks",
    "/actions",
    "/documents",
    "/analytics",
    "/notifications",
    "/settings",
    "/billing",
    "/workflows",
  ]) {
    await page.goto(path);
    await expect(page.locator("main h1")).toBeVisible();
    await expect(page.getByText("We couldn't load this")).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});

test("create contact, record a preference, and see timeline", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/contacts");
  await page.getByRole("button", { name: "Add contact", exact: true }).click();
  const name = "Browser Buyer " + Date.now();
  await page.getByLabel("Full name", { exact: true }).fill(name);
  await page
    .getByLabel("Email address", { exact: true })
    .fill(`browser-${Date.now()}@example.com`);
  await page.getByLabel("Relationship", { exact: true }).selectOption("buyer");
  await page
    .getByRole("button", { name: "Create contact", exact: true })
    .click();
  await page
    .getByRole("link", { name: new RegExp(name) })
    .first()
    .click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Maximum budget").fill("680000");
  await page.getByLabel("Preferred location").fill("Hartford");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText(/\$680,000/)).toBeVisible();
  await page.getByRole("button", { name: "Log activity" }).click();
  await page
    .getByLabel("Title", { exact: true })
    .fill("Buyer consultation completed");
  await page
    .getByLabel("Notes", { exact: true })
    .fill("Confirmed the search area and budget.");
  await page.getByRole("button", { name: "Add to timeline" }).click();
  await expect(
    page.getByRole("heading", { name: "Buyer consultation completed" }),
  ).toBeVisible();
});

test("structured command uses actual records", async ({ page }) => {
  await signIn(page);
  await page.goto("/command");
  await page
    .getByRole("button", { name: "Show buyers under $700k", exact: true })
    .click();
  await expect(
    page.getByText(/matching contacts in your workspace/),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /Olivia Chen/ })).toBeVisible();
});

test("approval executes once and appears in timeline", async ({ page }) => {
  await signIn(page);
  const proposal = await page.evaluate(async () => {
    const csrf = decodeURIComponent(
      document.cookie
        .split("; ")
        .find((v) => v.startsWith("realty_csrf="))!
        .split("=")[1],
    );
    const contacts = await fetch("/api/v1/crm/contacts?kind=buyer").then((r) =>
      r.json(),
    );
    const title = "Browser-reviewed task " + Date.now();
    const response = await fetch("/api/v1/actions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({
        kind: "create_task",
        title,
        reason: "Explicit task proposed during automated browser validation.",
        contact_id: contacts.items[0].id,
        payload: { title, contact_id: contacts.items[0].id },
      }),
    });
    return response.json();
  });
  await page.goto("/actions");
  const card = page
    .locator("article")
    .filter({
      has: page.getByRole("heading", { name: proposal.title, exact: true }),
    });
  await card.getByRole("button", { name: "Review suggestion" }).click();
  await page
    .getByRole("button", { name: "Approve action", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        page.evaluate(async (id) => {
          const data = await fetch("/api/v1/actions").then((r) => r.json());
          return data.items.find((a: { id: string }) => a.id === id)?.status;
        }, proposal.id),
      { timeout: 20000 },
    )
    .toBe("succeeded");
  await page.goto("/contacts/" + proposal.contact_id);
  await expect(
    page.getByRole("heading", { name: proposal.title, exact: true }),
  ).toBeVisible();
});

test("unconfigured Google never appears connected", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings");
  await page
    .getByRole("button", { name: "Connect Google", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Google integration is not configured.",
  );
});

test("account creation starts with an empty organization", async ({ page }) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page.getByLabel("Full name").fill("New Agent");
  await page.getByLabel("Organization", { exact: true }).fill("Browser Agency");
  await page.getByLabel("Email address").fill(`new-${Date.now()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Browser-test-password-123");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: /Good (morning|afternoon|evening), New/,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Nothing waiting on you" }),
  ).toBeVisible();
});
