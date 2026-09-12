import { afterEach, beforeEach, test, mock } from "node:test";
import assert from "node:assert/strict";
import {
  api,
  ApiError,
  date,
  parsedDate,
  retryAfterSeconds,
  retryRead,
  time,
} from "../frontend/api.ts";

beforeEach(() => {
  globalThis.document = { cookie: "" };
});
afterEach(() => {
  mock.restoreAll();
  delete globalThis.document;
});
function browser(response, cookie = "realty_csrf=test-token") {
  mock.property(globalThis, "document", { cookie });
  return mock.method(globalThis, "fetch", async () => response);
}

test("JSON requests preserve Headers, credentials and CSRF", async () => {
  const fetch = browser(Response.json({ id: "one" }));
  assert.deepEqual(
    await api("/contacts", {
      headers: new Headers({ "X-Request-ID": "request" }),
    }),
    { id: "one" },
  );
  const [url, options] = fetch.mock.calls[0].arguments;
  assert.equal(url, "/api/v1/contacts");
  assert.equal(options.credentials, "include");
  assert.equal(options.headers.get("X-Request-ID"), "request");
  assert.equal(options.headers.get("X-CSRF-Token"), "test-token");
});

test("invalid cookie encoding does not crash requests", async () => {
  const fetch = browser(Response.json({}), "realty_csrf=%E0%A4%A");
  await api("/config");
  assert.equal(
    fetch.mock.calls[0].arguments[1].headers.get("X-CSRF-Token"),
    "",
  );
});

test("multipart uploads let fetch supply the boundary", async () => {
  const fetch = browser(Response.json({}));
  await api("/documents", { method: "POST", body: new FormData() });
  assert.equal(
    fetch.mock.calls[0].arguments[1].headers.has("Content-Type"),
    false,
  );
});

test("empty successful responses are accepted", async () => {
  browser(new Response(null, { status: 204 }));
  assert.equal(await api("/resource", { method: "DELETE" }), undefined);
});

test("upstream HTML never becomes an error message or parser exception", async () => {
  browser(
    new Response("<html>private proxy diagnostics</html>", { status: 503 }),
  );
  await assert.rejects(
    api("/contacts"),
    (error) =>
      error instanceof ApiError &&
      error.status === 503 &&
      !error.message.includes("private"),
  );
});

test("malformed successful responses are reported distinctly", async () => {
  browser(new Response("not JSON"));
  await assert.rejects(
    api("/contacts"),
    (error) => error.code === "invalid_response",
  );
});

test("server rejection retains its safe error and retry interval", async () => {
  browser(
    Response.json(
      { error: { code: "rate_limited", message: "Please wait." } },
      { status: 429, headers: { "Retry-After": "20" } },
    ),
  );
  await assert.rejects(
    api("/contacts"),
    (error) =>
      error.code === "rate_limited" &&
      error.message === "Please wait." &&
      error.retryAfter === 20,
  );
});

test("an interrupted mutation is never automatically repeated", async () => {
  browser(Response.json({}));
  const fetch = mock.method(globalThis, "fetch", async () => {
    throw new TypeError("offline");
  });
  await assert.rejects(
    api("/actions/id/decision", { method: "POST", body: "{}" }),
    (error) =>
      error.code === "network_unavailable" &&
      error.message.includes("whether your change was saved"),
  );
  assert.equal(fetch.mock.callCount(), 1);
});

test("query cancellation is propagated without being disguised as a failure", async () => {
  browser(Response.json({}));
  const controller = new AbortController();
  controller.abort();
  const aborted = new DOMException("cancelled", "AbortError");
  mock.method(globalThis, "fetch", async () => {
    throw aborted;
  });
  await assert.rejects(
    api("/contacts", { signal: controller.signal }),
    (error) => error === aborted,
  );
});

test("read retries are bounded and respect server backoff", () => {
  assert.equal(
    retryRead(0, new ApiError(503, "unavailable", "Unavailable")),
    true,
  );
  assert.equal(
    retryRead(1, new ApiError(503, "unavailable", "Unavailable")),
    false,
  );
  assert.equal(
    retryRead(0, new ApiError(503, "unavailable", "Unavailable", 60)),
    false,
  );
  for (const status of [400, 401, 403, 404, 409, 422, 429]) {
    assert.equal(
      retryRead(0, new ApiError(status, "rejected", "Rejected")),
      false,
    );
  }
});

test("retry intervals accept seconds and HTTP dates, not malformed numbers", () => {
  mock.method(Date, "now", () => Date.parse("2026-09-12T00:00:00Z"));
  assert.equal(retryAfterSeconds("3"), 3);
  assert.equal(retryAfterSeconds("Sat, 12 Sep 2026 00:00:10 GMT"), 10);
  assert.equal(retryAfterSeconds("unavailable"), null);
});

test("dates with either signed offset refer to the same instant", () => {
  const instant = Date.parse("2026-09-12T16:00:00Z");
  for (const value of [
    "2026-09-12T12:00:00-04:00",
    "2026-09-12T18:00:00+02:00",
    "2026-09-12T16:00:00",
    "2026-09-12T16:00:00Z",
  ]) {
    assert.equal(parsedDate(value).getTime(), instant);
    assert.equal(time(value, "UTC"), "4:00 PM");
  }
  assert.equal(date("invalid"), "Not set");
  assert.equal(date(null), "Not set");
});
