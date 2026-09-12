import { expect, test, type BrowserContext, type Page } from "@playwright/test";

// Exercise sign-in once per worker, then reuse its real server session. Account
// recovery tests separately cover authentication without tripping abuse limits.
let demoCookies: Awaited<ReturnType<BrowserContext["cookies"]>> | undefined;

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

async function signIn(page: Page) {
  if (demoCookies) await page.context().addCookies(demoCookies);
  await page.goto("/");
  if (!demoCookies)
    await page.getByRole("button", { name: "Explore demo workspace" }).click();
  await expect(
    page.getByRole("heading", {
      name: /Good (morning|afternoon|evening), Sarah/,
    }),
  ).toBeVisible();
  demoCookies = await page.context().cookies();
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
    .include('[role="dialog"]')
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

test("demo dashboard, navigation and mobile fit", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await signIn(page);
  await page.getByRole("button", { name: "Dismiss notification" }).click();
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
    await expect(page.locator("main [role='status']")).toHaveCount(0);
    await expect(page.getByText("We couldn't load this")).toHaveCount(0);
    const layout = await page.evaluate(() => ({
      viewport: window.innerWidth,
      document: document.documentElement.scrollWidth,
    }));
    if (
      layout.viewport > page.viewportSize()!.width ||
      layout.document > layout.viewport
    ) {
      await testInfo.attach(`layout-${path.slice(1)}.json`, {
        contentType: "application/json",
        body: JSON.stringify(
          await page.evaluate(() =>
            Array.from(
              document.querySelectorAll(
                "body, #root, .app-shell, .main-shell, main, .section-card, .table-scroll, table, .pager",
              ),
            ).map((element) => {
              const rect = element.getBoundingClientRect();
              const style = getComputedStyle(element);
              return {
                tag: element.tagName,
                class: element.className,
                width: rect.width,
                right: rect.right,
                scrollWidth: element.scrollWidth,
                overflow: style.overflow,
                display: style.display,
                minWidth: style.minWidth,
                maxWidth: style.maxWidth,
                contain: style.contain,
              };
            }),
          ),
          null,
          2,
        ),
      });
    }
    expect(
      layout.viewport,
      `${path}: layout viewport must fit the device`,
    ).toBeLessThanOrEqual(page.viewportSize()!.width);
    expect(
      layout.document,
      `${path}: page must not scroll horizontally`,
    ).toBeLessThanOrEqual(layout.viewport);
  }
  expect(errors).toEqual([]);
});

test("failed demo email stays unsent and can return for review", async ({
  page,
}) => {
  await signIn(page);
  const csrf = (await page.context().cookies()).find(
    (c) => c.name === "realty_csrf",
  )!.value;
  const headers = { "x-csrf-token": csrf };
  const contacts = await page.request.get("/api/v1/crm/contacts?page_size=25");
  const contact = (await contacts.json()).items.find(
    (c: { email: string | null }) => c.email,
  );
  const created = await page.request.post("/api/v1/actions", {
    headers,
    data: {
      kind: "send_email",
      title: "Review failed demo delivery",
      reason: "Browser regression for safe demo sending",
      contact_id: contact.id,
      payload: { to: contact.email, subject: "Never sent", body: "Demo only" },
    },
  });
  expect(created.status()).toBe(201);
  const action = await created.json();
  const approved = await page.request.post(
    `/api/v1/actions/${action.id}/decision`,
    { headers, data: { decision: "approve", version: action.version } },
  );
  expect(approved.ok()).toBeTruthy();
  await expect
    .poll(
      async () => {
        const result = await page.request.get("/api/v1/actions?status=failed");
        return (await result.json()).items.some(
          (a: { id: string }) => a.id === action.id,
        );
      },
      { intervals: [1000], timeout: 15000 },
    )
    .toBeTruthy();
  await page.goto("/actions");
  await page.getByRole("button", { name: "Needs review", exact: true }).click();
  const card = page
    .locator(".action-card")
    .filter({ hasText: "Review failed demo delivery" });
  await expect(card).toBeVisible();
  await expect(card.getByText(/Google unconfigured/i)).toBeVisible();
  await card.getByRole("button", { name: "View details" }).click();
  await page.getByRole("button", { name: "Return for a new review" }).click();
  await page.getByRole("button", { name: "To review", exact: true }).click();
  await expect(
    page.getByText("Review failed demo delivery", { exact: true }),
  ).toBeVisible();
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
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
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
  const card = page.locator("article").filter({
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

test("review a CSV listing import and find the saved property", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/properties");
  const reference = `browser-${Date.now()}`;
  const address = `12 ${reference} Lane`;
  await page
    .getByRole("button", { name: "Import listings", exact: true })
    .click();
  await page.getByLabel("Listing file").setInputFiles({
    name: "listings.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      `reference,updated_at,address,location,price,bedrooms,bathrooms,features\n${reference},2026-01-01T00:00:00Z,${address},Example City,575000,3,2,garage;garden\n`,
    ),
  });
  await page.getByRole("button", { name: "Preview listings" }).click();
  await expect(
    page.getByRole("dialog").getByText(address, { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Import reviewed listings" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByPlaceholder("Search property addresses").fill(address);
  await expect(
    page.getByRole("button", { name: address, exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByPlaceholder("Search property addresses").fill(address);
  await expect(
    page.getByRole("button", { name: address, exact: true }),
  ).toBeVisible();
});
