import { createHmac } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

function totp(secret: string) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits = [...secret.replace(/=/g, "")]
    .map((c) => alphabet.indexOf(c).toString(2).padStart(5, "0"))
    .join("");
  const key = Buffer.from(
    bits.match(/.{8}/g)!.map((value) => parseInt(value, 2)),
  );
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const digest = createHmac("sha1", key).update(counter).digest();
  const offset = digest[digest.length - 1] & 15;
  return ((digest.readUInt32BE(offset) & 0x7fffffff) % 1000000)
    .toString()
    .padStart(6, "0");
}

async function signOut(page: Page) {
  await page.goto("/settings");
  await page.getByRole("button", { name: "Security", exact: true }).click();
  await page
    .getByRole("button", { name: "Sign out all devices", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Confirm sign out", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
}

test.beforeEach(async ({ request }) => {
  expect(
    (await (await request.get("/api/v1/config")).json()).demo_mode,
    "Run browser tests only on an isolated demo",
  ).toBe(true);
});

test("authenticator enrollment, session revocation and password recovery", async ({
  page,
}) => {
  test.setTimeout(60000);
  const email = `security-${Date.now()}@example.com`;
  const password = "Browser-security-password-123";
  await page.goto("/");
  await page
    .getByRole("button", { name: "New here? Create an account" })
    .click();
  await page.getByLabel("Full name").fill("Avery Agent");
  await page
    .getByLabel("Organization", { exact: true })
    .fill("Security Test Agency");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: /Good (morning|afternoon|evening), Avery/,
    }),
  ).toBeVisible();
  await page.goto("/settings");
  await page.getByRole("button", { name: "Security", exact: true }).click();
  await page.getByRole("button", { name: "Set up authenticator" }).click();
  await page.getByLabel("Current password").fill(password);
  await page.getByRole("button", { name: "Continue setup" }).click();
  const secret = await page.locator(".setup-key").innerText();
  await page
    .getByLabel("Authenticator code", { exact: true })
    .fill(totp(secret));
  await page
    .getByRole("button", { name: "Enable authenticator", exact: true })
    .click();
  const codes = (await page.locator(".recovery-codes").innerText()).split("\n");
  expect(codes).toHaveLength(10);
  await page.getByRole("button", { name: "I saved my codes" }).click();
  await expect(
    page.getByText("Authenticator enabled", { exact: true }),
  ).toBeVisible();
  await signOut(page);
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Authenticator or recovery code").fill(codes[0]);
  await page.getByRole("button", { name: "Verify sign in" }).click();
  await expect(
    page.getByRole("heading", {
      name: /Good (morning|afternoon|evening), Avery/,
    }),
  ).toBeVisible();
  await signOut(page);
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await page.getByLabel("Email address").fill(email);
  await page.getByRole("button", { name: "Send recovery email" }).click();
  await expect(page.locator("main").getByRole("status")).toContainText(
    "recovery email",
  );
  // Only the test runner can read this local outbox. No token-retrieval API exists.
  const directory = resolve(
    process.env.MAIL_OUTBOX_PATH || "data/account-mail",
  );
  let recoveryUrl = "";
  await expect
    .poll(
      () => {
        if (!existsSync(directory)) return "";
        for (const name of readdirSync(directory)) {
          const mail = readFileSync(join(directory, name), "utf8")
            .replace(/=\r?\n/g, "")
            .replace(/=3D/g, "=");
          if (mail.includes(`To: ${email}`) && mail.includes("#reset=")) {
            recoveryUrl = mail.match(/http[^\s]+#reset=[\w-]+/)?.[0] || "";
          }
        }
        return recoveryUrl;
      },
      { timeout: 20000 },
    )
    .not.toBe("");
  await page.goto(recoveryUrl);
  await page
    .getByLabel("New password", { exact: true })
    .fill(password + "-changed");
  await page.getByLabel("Confirm new password").fill(password + "-changed");
  await page.getByLabel("Authenticator or recovery code").fill(codes[1]);
  await page
    .getByRole("button", { name: "Reset password", exact: true })
    .click();
  await expect(page.locator("main").getByRole("status")).toContainText(
    "password is updated",
  );
  await page.getByRole("link", { name: "Return to sign in" }).click();
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill(password + "-changed");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Authenticator or recovery code").fill(codes[2]);
  await page.getByRole("button", { name: "Verify sign in" }).click();
  await expect(
    page.getByRole("heading", {
      name: /Good (morning|afternoon|evening), Avery/,
    }),
  ).toBeVisible();
});

test("automated accessibility and keyboard dialog behavior", async ({
  page,
}, info) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Explore demo workspace" }).click();
  await expect(
    page.getByRole("heading", {
      name: /Good (morning|afternoon|evening), Sarah/,
    }),
  ).toBeVisible();
  for (const path of ["/", "/contacts", "/settings"]) {
    await page.goto(path);
    await expect(page.locator("#main h1")).toBeVisible();
    await expect(page.locator("main [role='status']")).toHaveCount(0);
    if (path === "/settings")
      await page.getByRole("button", { name: "Security", exact: true }).click();
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    await info.attach(`accessibility-${path.slice(1) || "dashboard"}.json`, {
      body: JSON.stringify(result.violations, null, 2),
      contentType: "application/json",
    });
    expect(result.violations).toEqual([]);
  }
  await page.goto("/contacts");
  await page.getByRole("button", { name: "Add contact", exact: true }).click();
  await expect(page.getByLabel("Full name", { exact: true })).toBeFocused();
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(result.violations).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Add contact", exact: true }),
  ).toBeFocused();
});
