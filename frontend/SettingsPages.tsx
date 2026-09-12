import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Check,
  CreditCard,
  Download,
  ExternalLink,
  LockKeyhole,
  Mail,
  Plus,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Workflow as WorkflowIcon,
} from "lucide-react";
import { useSession } from "./App";
import AccountSecurity from "./AccountSecurity";
import { api, date, post, put, useApi, words } from "./api";
import {
  Badge,
  Button,
  Empty,
  ErrorState,
  Field,
  Loading,
  Modal,
  PageTitle,
  Submit,
  useAction,
} from "./components";
import type {
  Audit,
  Integrations,
  Job,
  Page,
  Subscription,
  Workflow,
} from "./types";

export default function SettingsPages({ page }: { page: string }) {
  return page === "billing" ? (
    <Billing />
  ) : page === "workflows" ? (
    <Workflows />
  ) : (
    <Settings />
  );
}
function Settings() {
  const query = useApi<Integrations>("/integrations");
  const session = useSession();
  const { busy, run } = useAction();
  const [tab, setTab] = useState("connections");
  const [deleteOpen, setDeleteOpen] = useState(false);
  async function connect(capability: string) {
    const result = await run(
      () =>
        post<{ url: string }>(
          "/integrations/google/authorize?capability=" + capability,
        ),
      "Opening Google authorization.",
    );
    if (result) window.location.assign(result.url);
  }
  async function exportData() {
    const data = await run(
      () => api("/account/export"),
      "Your export is ready.",
    );
    if (data) {
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "realtyai-export.json";
      a.click();
      URL.revokeObjectURL(url);
    }
  }
  return (
    <>
      <PageTitle
        eyebrow="YOUR WORKSPACE, YOUR WAY"
        title="Settings"
        description="Connections, people and the controls that keep your business yours."
      />
      <div className="tabs">
        {["connections", "team", "activity", "security", "account"].map((t) => (
          <button
            key={t}
            className={tab === t ? "active" : ""}
            onClick={() => setTab(t)}
          >
            {words(t)}
          </button>
        ))}
      </div>
      {tab === "security" && <AccountSecurity />}
      {tab === "connections" &&
        (query.isLoading ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : (
          <div className="settings-grid">
            <section className="section-card integration-card">
              <div className="integration-heading">
                <span className="integration-icon">
                  <Mail size={25} />
                </span>
                <div>
                  <h2>Google Workspace</h2>
                  <p>Gmail and Google Calendar</p>
                </div>
                <Badge
                  tone={
                    query.data?.connections.some(
                      (c) => c.status === "connected",
                    )
                      ? "green"
                      : "neutral"
                  }
                >
                  {query.data?.connections.some((c) => c.status === "connected")
                    ? "Connected"
                    : query.data?.google_configured
                      ? "Available"
                      : "Not configured"}
                </Badge>
              </div>
              <p>
                Bring relevant conversations and appointments into your client
                relationships. Sending email and changing Google events require
                separate permissions and your approval.
              </p>
              {query.data?.connections.map((c) => (
                <div className="connection-details" key={c.id}>
                  <strong>{c.email}</strong>
                  <span>
                    {c.status} · Last sync {date(c.last_sync_at)}
                  </span>
                  {c.last_error && (
                    <span className="error-text">{words(c.last_error)}</span>
                  )}
                </div>
              ))}
              <div className="button-group">
                <Button
                  variant="primary"
                  disabled={busy}
                  onClick={() => connect("read")}
                >
                  Connect Google <ExternalLink size={15} />
                </Button>
                <Button disabled={busy} onClick={() => connect("send")}>
                  Enable email sending
                </Button>
                <Button
                  disabled={busy}
                  onClick={() => connect("calendar_write")}
                >
                  Enable calendar changes
                </Button>
              </div>
              {query.data?.connections.some(
                (c) => c.status === "connected",
              ) && (
                <Button
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => post("/integrations/google/disconnect"),
                      "Google disconnected. Previously synced CRM records were retained.",
                    )
                  }
                >
                  Disconnect Google
                </Button>
              )}
              {!query.data?.google_configured && (
                <p className="configuration-notice">
                  Google integration is not configured. Add the Google OAuth
                  credentials and encryption key to the server environment to
                  enable connection.
                </p>
              )}
              <small>
                Disconnecting revokes access. Previously synchronized CRM data
                stays available until explicitly deleted.
              </small>
            </section>
            <section className="section-card integration-card">
              <div className="integration-heading">
                <span className="integration-icon">
                  <Sparkles size={25} />
                </span>
                <div>
                  <h2>AI provider</h2>
                  <p>Analysis and grounded answers</p>
                </div>
                <Badge tone={query.data?.ai_configured ? "green" : "neutral"}>
                  {query.data?.ai_configured ? "Configured" : "Not configured"}
                </Badge>
              </div>
              <p>
                Structured search and record-based briefings work without an AI
                provider. Open-ended answers, advanced extraction and document
                summaries use the configured provider.
              </p>
              <div className="security-points">
                <span>
                  <ShieldCheck size={17} />
                  Organization-scoped context
                </span>
                <span>
                  <LockKeyhole size={17} />
                  No unrestricted execution tools
                </span>
                <span>
                  <Check size={17} />
                  Validated output and source evidence
                </span>
              </div>
              <Link className="button secondary" to="/actions">
                Review action policy <ArrowRight size={15} />
              </Link>
            </section>
            <section className="section-card integration-card">
              <div className="integration-heading">
                <span className="integration-icon">
                  <WorkflowIcon size={24} />
                </span>
                <div>
                  <h2>Workflow rules</h2>
                  <p>Consistent follow-through</p>
                </div>
              </div>
              <p>
                Turn a new lead, a property match or an overdue follow-up into
                an internal notification or a suggestion for review.
              </p>
              <Link to="/workflows" className="button secondary">
                Manage workflows <ArrowRight size={15} />
              </Link>
            </section>
            <section className="section-card integration-card">
              <h2>Future connections</h2>
              <p>
                Call transcription and scanned-document OCR have provider
                interfaces. No live telephony or OCR provider is configured in
                this build.
              </p>
              <Badge>Not available</Badge>
            </section>
          </div>
        ))}
      {tab === "team" && <Team />}
      {tab === "activity" && <Operations />}
      {tab === "account" && (
        <section className="section-card account-card">
          <h2>{session.organization.name}</h2>
          <p>
            {session.user.name} · {session.user.email}
          </p>
          <Badge>{session.role}</Badge>
          <h3>Your data</h3>
          <p>
            Export the organization's CRM records, source facts, actions and
            audit history.
          </p>
          <Button disabled={busy} onClick={exportData}>
            <Download size={17} />
            Export workspace
          </Button>
          <div className="danger-zone">
            <h3>Delete organization</h3>
            <p>
              Disconnect all Google accounts and cancel any active subscription
              first. Deletion removes the organization's records and documents
              permanently.
            </p>
            <Button variant="danger" onClick={() => setDeleteOpen(true)}>
              Delete organization
            </Button>
          </div>
        </section>
      )}
      {deleteOpen && (
        <Modal
          title="Permanently delete this organization?"
          onClose={() => setDeleteOpen(false)}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              const data = Object.fromEntries(new FormData(e.currentTarget));
              const result = await run(
                () => post("/account/delete", data),
                "Organization deleted.",
              );
              if (result) window.location.assign("/");
            }}
          >
            <p>
              This cannot be undone. Enter the organization name and your
              password to confirm.
            </p>
            <Field label={"Type " + session.organization.name}>
              <input name="organization_name" required />
            </Field>
            <Field label="Your password">
              <input
                name="password"
                type="password"
                required
                autoComplete="current-password"
              />
            </Field>
            {session.user.mfa_enabled && (
              <Field label="Authenticator or recovery code">
                <input
                  name="code"
                  autoComplete="one-time-code"
                  required
                  maxLength={40}
                />
              </Field>
            )}
            <Button type="submit" variant="danger" disabled={busy}>
              Permanently delete organization
            </Button>
          </form>
        </Modal>
      )}
    </>
  );
}
function Team() {
  const query = useApi<{
    items: { id: string; name: string; email: string; role: string }[];
  }>("/account/members");
  const [open, setOpen] = useState(false);
  const { busy, run } = useAction();
  const add = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.currentTarget));
    const result = await run(
      () => post("/account/members", data),
      "Member added.",
    );
    if (result) setOpen(false);
  };
  return (
    <section className="section-card">
      <div className="section-heading">
        <h2>Your team</h2>
        <Button onClick={() => setOpen(true)}>
          <Plus size={16} />
          Add member
        </Button>
      </div>
      {query.error ? (
        <ErrorState error={query.error} />
      ) : (
        query.data?.items.map((m) => (
          <div className="team-row" key={m.id}>
            <div>
              <strong>{m.name}</strong>
              <small>{m.email}</small>
            </div>
            {m.role === "owner" ? (
              <Badge tone="green">Owner</Badge>
            ) : (
              <select
                aria-label={"Role for " + m.name}
                value={m.role}
                onChange={(e) =>
                  run(
                    () =>
                      put("/account/members/" + m.id, {
                        email: m.email,
                        role: e.target.value,
                      }),
                    "Role updated.",
                  )
                }
                disabled={busy}
              >
                {["admin", "agent", "assistant", "viewer"].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            )}
          </div>
        ))
      )}
      {open && (
        <Modal title="Add a team member" onClose={() => setOpen(false)}>
          <p>
            The person must already have a RealtyAI account. No invitation email
            will be sent.
          </p>
          <form onSubmit={add}>
            <Field label="Account email">
              <input name="email" type="email" required />
            </Field>
            <Field label="Role">
              <select name="role">
                {["agent", "assistant", "viewer", "admin"].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </Field>
            <Submit busy={busy} label="Add member" />
          </form>
        </Modal>
      )}
    </section>
  );
}
function Operations() {
  const health = useApi<{
    worker_available: boolean;
    oldest_due_seconds: number;
    storage_cleanup_failures: number;
  }>("/operations");
  const jobs = useApi<Page<Job>>("/jobs");
  const audit = useApi<Page<Audit>>("/audit");
  const { busy, run } = useAction();
  return (
    <div className="operations-grid">
      <section className="section-card">
        <div className="section-heading">
          <h2>Background work</h2>
          <Button
            aria-label="Refresh background jobs"
            onClick={() => {
              jobs.refetch();
              health.refetch();
            }}
          >
            <RefreshCw size={15} />
          </Button>
        </div>
        {health.data && (
          <p>
            <Badge tone={health.data.worker_available ? "green" : "amber"}>
              {health.data.worker_available
                ? "Worker available"
                : "Worker needs attention"}
            </Badge>{" "}
            · Oldest waiting job: {health.data.oldest_due_seconds}s
            {health.data.storage_cleanup_failures > 0 &&
              " · File cleanup needs attention"}
          </p>
        )}
        {jobs.error ? (
          <ErrorState error={jobs.error} />
        ) : jobs.data?.items.length ? (
          jobs.data.items.map((j) => (
            <div className="job-row" key={j.id}>
              <div>
                <strong>{words(j.kind)}</strong>
                <small>
                  {j.attempts} attempts{" "}
                  {j.error_code && "· " + words(j.error_code)}
                </small>
              </div>
              <Badge
                tone={
                  j.status === "done"
                    ? "green"
                    : j.status === "dead"
                      ? "red"
                      : "neutral"
                }
              >
                {j.status}
              </Badge>
              {j.status === "dead" && j.kind !== "execute_action" && (
                <Button
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => post("/jobs/" + j.id + "/retry"),
                      "Job queued for retry.",
                    )
                  }
                >
                  Retry
                </Button>
              )}
            </div>
          ))
        ) : (
          <Empty
            title="No background work yet"
            body="Sync and approved actions create tracked jobs."
          />
        )}
      </section>
      <section className="section-card">
        <div className="section-heading">
          <h2>Audit history</h2>
        </div>
        {audit.error ? (
          <ErrorState error={audit.error} />
        ) : (
          audit.data?.items.map((a) => (
            <div className="audit-row" key={a.id}>
              <ShieldCheck size={17} />
              <div>
                <strong>{a.action}</strong>
                <small>
                  {date(a.created_at)} · {a.result}
                </small>
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  );
}
function Billing() {
  const query = useApi<{
    subscription: Subscription | null;
    configured: boolean;
  }>("/billing");
  const { busy, run } = useAction();
  const open = async (path: string) => {
    const result = await run(
      () => post<{ url: string }>(path),
      "Opening secure billing.",
    );
    if (result) window.location.assign(result.url);
  };
  return (
    <>
      <PageTitle
        eyebrow="GROW AT YOUR PACE"
        title="Billing & subscription"
        description="A clear view of your plan and account status."
      />
      {query.isLoading ? (
        <Loading />
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : (
        <div className="billing-grid">
          <section className="billing-plan">
            <span className="plan-icon">
              <Sparkles size={27} />
            </span>
            <Badge>YOUR PLAN</Badge>
            <h2>{words(query.data?.subscription?.plan || "Trial")}</h2>
            <p>
              Client relationships, actionable intelligence and approval-driven
              assistance.
            </p>
            <div className="plan-status">
              <strong>
                {words(query.data?.subscription?.status || "Unknown")}
              </strong>
              <span>
                {query.data?.subscription?.trial_end
                  ? "Trial ends " + date(query.data.subscription.trial_end)
                  : "Current period ends " +
                    date(query.data?.subscription?.period_end)}
              </span>
            </div>
            <Button
              variant="light"
              disabled={busy}
              onClick={() =>
                open("/billing/checkout?request_id=" + crypto.randomUUID())
              }
            >
              Manage your plan <ArrowRight size={17} />
            </Button>
          </section>
          <section className="section-card billing-details">
            <h2>
              <CreditCard size={22} />
              Billing details
            </h2>
            <p>
              Payment methods, invoices, plan changes and cancellation are
              managed securely through Stripe.
            </p>
            <Button disabled={busy} onClick={() => open("/billing/portal")}>
              Open billing portal <ExternalLink size={15} />
            </Button>
            {!query.data?.configured && (
              <p className="configuration-notice">
                Billing integration is not configured. Configure the Stripe
                secret, webhook secret and price before accepting payments. This
                workspace has not been charged.
              </p>
            )}
            <h3>Included controls</h3>
            <ul className="plan-features">
              <li>
                <Check size={17} />
                Server-verified subscription state
              </li>
              <li>
                <Check size={17} />
                Measured AI usage and limits
              </li>
              <li>
                <Check size={17} />
                No payment details stored in RealtyAI
              </li>
            </ul>
          </section>
        </div>
      )}
    </>
  );
}
function Workflows() {
  const query = useApi<Page<Workflow>>("/workflows");
  const [open, setOpen] = useState(false);
  const { busy, run } = useAction();
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.currentTarget));
    const result = await run(
      () =>
        post("/workflows", {
          name: d.name,
          trigger: d.trigger,
          action: d.action,
          condition: { min_score: Number(d.min_score) },
        }),
      "Workflow created.",
    );
    if (result) setOpen(false);
  };
  return (
    <>
      <PageTitle
        eyebrow="CONSISTENT FOLLOW-THROUGH"
        title="Workflow rules"
        description="Observe an event, check the conditions, prepare a suggestion, record the outcome."
        action={
          <Button variant="primary" onClick={() => setOpen(true)}>
            <Plus size={17} />
            Create rule
          </Button>
        }
      />
      <div className="workflow-steps">
        {[
          "Business event",
          "Conditions",
          "Suggested action",
          "Your approval",
          "Execution & audit",
        ].map((s, i) => (
          <span key={s}>
            <strong>{i + 1}</strong>
            {s}
            {i < 4 && <ArrowRight size={16} />}
          </span>
        ))}
      </div>
      <section className="section-card">
        {query.error ? (
          <ErrorState error={query.error} />
        ) : (
          query.data?.items.map((w) => (
            <div className="workflow-row" key={w.id}>
              <span className="integration-icon">
                <Settings2 size={21} />
              </span>
              <div>
                <h3>{w.name}</h3>
                <p>
                  {words(w.trigger)} → {words(w.action)}
                </p>
                <small>
                  Minimum intent score: {w.condition.min_score || 0}
                </small>
              </div>
              <Button
                disabled={busy}
                onClick={() =>
                  run(
                    () =>
                      put("/workflows/" + w.id, {
                        name: w.name,
                        trigger: w.trigger,
                        action: w.action,
                        condition: w.condition,
                        enabled: !w.enabled,
                      }),
                    "Workflow updated.",
                  )
                }
              >
                {w.enabled ? "Pause rule" : "Enable rule"}
              </Button>
              <Badge tone={w.enabled ? "green" : "neutral"}>
                {w.enabled ? "Active" : "Paused"}
              </Badge>
            </div>
          ))
        )}
        {query.data && !query.data.items.length && (
          <Empty
            title="Start with one useful routine"
            body="Create a rule that prepares work for your review."
          />
        )}
      </section>
      {open && (
        <Modal title="Create a workflow rule" onClose={() => setOpen(false)}>
          <form onSubmit={save}>
            <Field label="Rule name">
              <input name="name" required />
            </Field>
            <Field label="When this happens">
              <select name="trigger">
                {[
                  "LEAD_CREATED",
                  "PROPERTY_CREATED",
                  "FOLLOW_UP_REQUIRED",
                  "EMAIL_RECEIVED",
                ].map((v) => (
                  <option key={v} value={v}>
                    {words(v)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Prepare this action">
              <select name="action">
                {["notify", "recommend_followup", "match_properties"].map(
                  (v) => (
                    <option key={v} value={v}>
                      {words(v)}
                    </option>
                  ),
                )}
              </select>
            </Field>
            <Field label="Minimum intent score">
              <input
                name="min_score"
                type="number"
                min="0"
                max="100"
                defaultValue="0"
              />
            </Field>
            <p>
              Rules prepare internal work. External actions always require a
              specific approval.
            </p>
            <Submit busy={busy} label="Create rule" />
          </form>
        </Modal>
      )}
    </>
  );
}
