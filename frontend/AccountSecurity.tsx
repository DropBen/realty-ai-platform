import { useEffect, useState, type FormEvent } from "react";
import { api, date, post, useApi } from "./api";
import {
  Badge,
  Button,
  ErrorState,
  Field,
  Loading,
  Modal,
  Submit,
  useAction,
} from "./components";

type Security = {
  email_verified: boolean;
  mfa_enabled: boolean;
  mail_backend: string;
  recovery_codes_remaining: number;
};
type Device = {
  id: string;
  created_at: string;
  expires_at: string;
  user_agent: string;
  current: boolean;
};

export default function AccountSecurity() {
  const state = useApi<Security>("/auth/security");
  const sessions = useApi<{ items: Device[] }>("/auth/sessions");
  const { busy, run } = useAction();
  const [mode, setMode] = useState("");
  const [enrollment, setEnrollment] = useState<{
    secret: string;
    uri: string;
  } | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  if (state.isLoading) return <Loading />;
  if (state.error) return <ErrorState error={state.error} />;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget));
    const result = await run(
      () =>
        post<{ secret?: string; uri?: string; recovery_codes?: string[] }>(
          mode === "password" ? "/auth/password/change" : "/auth/mfa/" + mode,
          body,
        ),
      mode === "password"
        ? "Password changed. Sign in again."
        : "Account security updated.",
      mode !== "password",
    );
    if (!result) return;
    if (mode === "password") {
      window.location.assign("/");
      return;
    }
    if (result.secret && result.uri) {
      setEnrollment({ secret: result.secret, uri: result.uri });
      setMode("confirm");
    } else {
      setEnrollment(null);
      setMode("");
    }
    if (result.recovery_codes) setCodes(result.recovery_codes);
  };
  return (
    <div className="security-sections">
      <section className="section-card security-card">
        <h2>Email and password</h2>
        <p>
          <Badge tone={state.data?.email_verified ? "green" : "amber"}>
            {state.data?.email_verified
              ? "Email verified"
              : "Email not verified"}
          </Badge>
        </p>
        {state.data?.mail_backend === "outbox" && (
          <p className="help-text">
            Development mail is saved in the local account-mail outbox. It is
            not sent externally.
          </p>
        )}
        {state.data?.mail_backend === "disabled" && (
          <p className="help-text">
            Email delivery needs configuration before verification or recovery
            links can be delivered.
          </p>
        )}
        <div className="button-group">
          {!state.data?.email_verified && (
            <Button
              disabled={busy}
              onClick={() =>
                run(
                  () => post("/auth/email/request"),
                  "Verification email queued.",
                )
              }
            >
              Request verification email
            </Button>
          )}
          <Button onClick={() => setMode("password")}>Change password</Button>
        </div>
      </section>
      <section className="section-card security-card">
        <h2>Two-factor authentication</h2>
        <p>
          Use an authenticator app to protect sign-in. Store recovery codes
          somewhere safe in case you lose access to your device.
        </p>
        <Badge tone={state.data?.mfa_enabled ? "green" : "neutral"}>
          {state.data?.mfa_enabled
            ? "Authenticator enabled"
            : "Authenticator not enabled"}
        </Badge>
        {state.data?.mfa_enabled && (
          <p>
            {state.data.recovery_codes_remaining} unused recovery codes remain.
          </p>
        )}
        <div className="button-group">
          {state.data?.mfa_enabled ? (
            <>
              <Button onClick={() => setMode("recovery-codes")}>
                Replace recovery codes
              </Button>
              <Button onClick={() => setMode("disable")}>
                Disable authenticator
              </Button>
            </>
          ) : (
            <Button onClick={() => setMode("enroll")}>
              Set up authenticator
            </Button>
          )}
        </div>
      </section>
      <section className="section-card security-card">
        <h2>Signed-in devices</h2>
        <p>
          Browser descriptions help identify sessions; they are supplied by the
          browser and are not verified device identities.
        </p>
        {sessions.isLoading ? (
          <Loading />
        ) : sessions.error ? (
          <ErrorState error={sessions.error} />
        ) : (
          sessions.data?.items.map((device) => (
            <div className="device-row" key={device.id}>
              <div>
                <strong>
                  {device.current ? "This browser" : "Another session"}
                </strong>
                <p>{device.user_agent || "Browser details unavailable"}</p>
                <small>
                  Signed in {date(device.created_at)} · Expires{" "}
                  {date(device.expires_at)}
                </small>
              </div>
              {!device.current && (
                <Button
                  disabled={busy}
                  onClick={() =>
                    run(
                      () =>
                        api(`/auth/sessions/${device.id}`, {
                          method: "DELETE",
                        }),
                      "Session revoked.",
                    )
                  }
                >
                  Revoke session
                </Button>
              )}
            </div>
          ))
        )}
        <Button onClick={() => setMode("logout-all")}>
          Sign out all devices
        </Button>
      </section>
      {mode && (
        <Modal
          title={
            {
              password: "Change your password",
              enroll: "Set up an authenticator",
              confirm: "Confirm your authenticator",
              disable: "Disable your authenticator",
              "recovery-codes": "Replace recovery codes",
              "logout-all": "Sign out all devices?",
            }[mode] || "Account security"
          }
          onClose={() => {
            setMode("");
            setEnrollment(null);
          }}
        >
          {mode === "logout-all" ? (
            <>
              <p>
                This includes your current browser. You will need to sign in
                again.
              </p>
              <Button
                variant="primary"
                disabled={busy}
                onClick={async () => {
                  const result = await run(
                    () => post("/auth/sessions/revoke-all"),
                    "All sessions revoked.",
                    false,
                  );
                  if (result) window.location.assign("/");
                }}
              >
                Confirm sign out
              </Button>
            </>
          ) : (
            <form onSubmit={submit}>
              {enrollment && (
                <>
                  <p>
                    In your authenticator app, add a time-based account using
                    this setup key, then enter the generated six-digit code.
                  </p>
                  <code className="setup-key">{enrollment.secret}</code>
                  <p>
                    <a className="text-button" href={enrollment.uri}>
                      Open in an authenticator app
                    </a>
                  </p>
                </>
              )}
              {mode !== "confirm" && (
                <Field label="Current password">
                  <input
                    type="password"
                    name="password"
                    autoComplete="current-password"
                    required
                    maxLength={128}
                  />
                </Field>
              )}
              {mode === "password" && (
                <>
                  <Field
                    label="New password"
                    hint="Use at least 12 characters."
                  >
                    <input
                      type="password"
                      name="new_password"
                      required
                      minLength={12}
                      maxLength={128}
                      autoComplete="new-password"
                    />
                  </Field>
                  <Field label="Confirm new password">
                    <input
                      type="password"
                      name="confirm_password"
                      required
                      minLength={12}
                      maxLength={128}
                      autoComplete="new-password"
                    />
                  </Field>
                </>
              )}
              {(mode === "confirm" || state.data?.mfa_enabled) && (
                <Field
                  label={
                    mode === "confirm"
                      ? "Authenticator code"
                      : "Authenticator or recovery code"
                  }
                >
                  <input
                    name="code"
                    autoComplete="one-time-code"
                    required
                    maxLength={40}
                  />
                </Field>
              )}
              <Submit
                busy={busy}
                label={
                  mode === "confirm"
                    ? "Enable authenticator"
                    : mode === "enroll"
                      ? "Continue setup"
                      : "Confirm change"
                }
              />
            </form>
          )}
        </Modal>
      )}
      {codes && (
        <Modal title="Save your recovery codes" onClose={() => setCodes(null)}>
          <p>
            These codes are shown only once. Each code works once. Keep them
            outside this account, such as in your password manager.
          </p>
          <pre className="recovery-codes">{codes.join("\n")}</pre>
          <Button
            onClick={() => {
              const url = URL.createObjectURL(
                new Blob(
                  [
                    "RealtyAI recovery codes — keep private\n\n" +
                      codes.join("\n"),
                  ],
                  { type: "text/plain" },
                ),
              );
              const link = document.createElement("a");
              link.href = url;
              link.download = "realtyai-recovery-codes.txt";
              link.click();
              URL.revokeObjectURL(url);
            }}
          >
            Download codes
          </Button>
          <Button onClick={() => setCodes(null)}>I saved my codes</Button>
        </Modal>
      )}
    </div>
  );
}

export function VerificationRequired({ email }: { email: string }) {
  const { busy, run } = useAction();
  return (
    <main className="account-access">
      <section className="section-card security-card">
        <h1>Verify your email</h1>
        <p>
          Open the verification email sent to {email} before continuing to your
          workspace.
        </p>
        <Button
          disabled={busy}
          onClick={() =>
            run(
              () => post("/auth/email/request"),
              "A new verification email was queued.",
            )
          }
        >
          Resend verification email
        </Button>
        <Button onClick={() => window.location.reload()}>
          I verified my email
        </Button>
        <Button
          onClick={async () => {
            if (await run(() => post("/auth/logout"), "Signed out."))
              window.location.reload();
          }}
        >
          Sign out
        </Button>
      </section>
    </main>
  );
}

export function AccountAccess() {
  const [link, setLink] = useState(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const result = { reset: params.get("reset"), verify: params.get("verify") };
    return result;
  });
  const [done, setDone] = useState(false);
  useEffect(() => {
    const consumeLink = () => {
      const params = new URLSearchParams(window.location.hash.slice(1));
      const next = { reset: params.get("reset"), verify: params.get("verify") };
      if (next.reset || next.verify) {
        setLink(next);
        setDone(false);
      }
      window.history.replaceState(null, "", window.location.pathname);
    };
    consumeLink();
    window.addEventListener("hashchange", consumeLink);
    return () => window.removeEventListener("hashchange", consumeLink);
  }, []);
  const { busy, run } = useAction();
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget));
    const result = await run(
      () =>
        post(
          link.verify
            ? "/auth/email/verify"
            : link.reset
              ? "/auth/password/reset"
              : "/auth/password/request",
          link.verify
            ? { token: link.verify }
            : link.reset
              ? { ...body, token: link.reset }
              : body,
        ),
      link.verify
        ? "Email verified."
        : link.reset
          ? "Password reset. Sign in again."
          : "If an account is eligible, a recovery email will be delivered.",
    );
    if (result) setDone(true);
  };
  return (
    <main className="account-access">
      <section className="section-card security-card">
        <div className="eyebrow">REALTYAI ACCOUNT SECURITY</div>
        <h1>
          {link.verify
            ? "Verify your email"
            : link.reset
              ? "Choose a new password"
              : "Recover your account"}
        </h1>
        {done ? (
          <p role="status">
            {link.verify
              ? "Your email is verified."
              : link.reset
                ? "Your password is updated. All existing sessions have been signed out."
                : "If an account is eligible, a recovery email will be delivered. Check your inbox. "}
          </p>
        ) : (
          <form onSubmit={submit}>
            {!link.verify && !link.reset && (
              <Field label="Email address">
                <input
                  type="email"
                  name="email"
                  autoComplete="email"
                  required
                />
              </Field>
            )}
            {link.reset && (
              <>
                <Field label="New password">
                  <input
                    type="password"
                    name="new_password"
                    minLength={12}
                    maxLength={128}
                    autoComplete="new-password"
                    required
                  />
                </Field>
                <Field label="Confirm new password">
                  <input
                    type="password"
                    name="confirm_password"
                    minLength={12}
                    maxLength={128}
                    autoComplete="new-password"
                    required
                  />
                </Field>
                <Field
                  label="Authenticator or recovery code"
                  hint="Required if you enabled two-factor authentication."
                >
                  <input
                    name="code"
                    autoComplete="one-time-code"
                    maxLength={40}
                  />
                </Field>
              </>
            )}
            <Submit
              busy={busy}
              label={
                link.verify
                  ? "Verify email"
                  : link.reset
                    ? "Reset password"
                    : "Send recovery email"
              }
            />
          </form>
        )}
        <p>
          <a className="text-button" href="/">
            Return to sign in
          </a>
        </p>
      </section>
    </main>
  );
}
