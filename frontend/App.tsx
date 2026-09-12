import {
  createContext,
  lazy,
  Suspense,
  useContext,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  ArrowRight,
  Bell,
  Building2,
  CalendarDays,
  ChartNoAxesCombined,
  CheckCheck,
  ChevronDown,
  ChevronsUpDown,
  CircleHelp,
  Command,
  CreditCard,
  FileText,
  House,
  Inbox,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  Settings2,
  Sparkles,
  Users,
  Workflow,
  X,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, api, post, useApi } from "./api";
import {
  Avatar,
  Badge,
  Button,
  ErrorState,
  Field,
  Loading,
  Modal,
  Submit,
  useAction,
} from "./components";
import type { Session } from "./types";
import Dashboard from "./Dashboard";
import { AccountAccess, VerificationRequired } from "./AccountSecurity";

const Contacts = lazy(() => import("./Contacts"));
const Profile = lazy(() => import("./Profile"));
const WorkPages = lazy(() => import("./WorkPages"));
const SettingsPages = lazy(() => import("./SettingsPages"));
const SessionContext = createContext<Session | null>(null);
export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error("Session unavailable");
  return session;
}

const nav = [
  {
    label: "Overview",
    items: [
      ["Dashboard", "/", LayoutDashboard],
      ["AI command center", "/command", Sparkles],
      ["Inbox", "/inbox", Inbox],
    ],
  },
  {
    label: "Relationships",
    items: [
      ["Contacts", "/contacts", Users],
      ["Leads", "/leads", Users],
      ["Buyers", "/buyers", House],
      ["Sellers", "/sellers", Building2],
      ["Properties", "/properties", House],
      ["Deals", "/deals", Workflow],
    ],
  },
  {
    label: "Your workspace",
    items: [
      ["Calendar", "/calendar", CalendarDays],
      ["Tasks", "/tasks", CheckCheck],
      ["AI actions", "/actions", Sparkles],
      ["Documents", "/documents", FileText],
      ["Analytics", "/analytics", ChartNoAxesCombined],
    ],
  },
] as const;

function AuthScreen() {
  const queryClient = useQueryClient();
  const [mfa, setMfa] = useState(false);
  const [code, setCode] = useState("");
  const [register, setRegister] = useState(false);
  const [name, setName] = useState("");
  const [organization, setOrganization] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { busy, run } = useAction();
  const config = useApi<{ demo_mode: boolean }>("/config");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const result = await run(
      () =>
        post<{ mfa_required?: boolean }>(
          mfa
            ? "/auth/mfa/verify"
            : register
              ? "/auth/register"
              : "/auth/login",
          mfa
            ? { code }
            : register
              ? { name, organization, email, password }
              : { email, password },
        ),
      mfa ? "Sign-in verified." : "Sign-in request processed.",
      false,
    );
    if (result?.mfa_required) {
      setMfa(true);
      setPassword("");
    } else if (result) {
      await queryClient.invalidateQueries();
    }
  };
  return (
    <main className="auth-page">
      <div className="auth-story">
        <Link to="/" className="brand">
          <span className="brand-icon">
            <House />
          </span>
          realty<span>ai</span>
        </Link>
        <div>
          <div className="eyebrow">YOUR RELATIONSHIPS. YOUR ADVANTAGE.</div>
          <h1>
            More present.
            <br />
            Less busywork.
          </h1>
          <p>
            A clear view of your clients, your next move, and everything in
            between.
          </p>
          <div className="auth-principle">
            <Sparkles />
            <span>
              The AI handles the busywork.
              <br />
              <strong>You handle the relationship.</strong>
            </span>
          </div>
        </div>
        <small>
          Built around your judgment. Every consequential action stays in your
          hands.
        </small>
      </div>
      <section className="auth-form">
        <div className="auth-form-inner">
          <Badge tone="green">RealtyAI workspace</Badge>
          <h2>
            {register ? "Make room for your next chapter." : "Welcome back."}
          </h2>
          <p>
            {register
              ? "Create your organization to begin."
              : "Your relationships are ready when you are."}
          </p>
          <form onSubmit={submit}>
            {mfa ? (
              <Field
                label="Authenticator or recovery code"
                hint="Enter your six-digit authenticator code or an unused recovery code."
              >
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  autoComplete="one-time-code"
                  maxLength={40}
                  required
                  autoFocus
                />
              </Field>
            ) : (
              <>
                {register && (
                  <>
                    <Field label="Full name">
                      <input
                        autoComplete="name"
                        required
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                      />
                    </Field>
                    <Field label="Organization">
                      <input
                        autoComplete="organization"
                        required
                        value={organization}
                        onChange={(e) => setOrganization(e.target.value)}
                      />
                    </Field>
                  </>
                )}
                <Field label="Email address">
                  <input
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </Field>
                <Field
                  label="Password"
                  hint={register ? "Use at least 12 characters." : undefined}
                >
                  <input
                    type="password"
                    required
                    minLength={register ? 12 : 1}
                    autoComplete={
                      register ? "new-password" : "current-password"
                    }
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </Field>
              </>
            )}
            <Submit
              busy={busy}
              label={
                mfa ? "Verify sign in" : register ? "Create account" : "Sign in"
              }
            />
          </form>
          {!register && (
            <p>
              <a className="text-button" href="/account-access">
                Forgot your password?
              </a>
            </p>
          )}
          <button
            className="text-button"
            onClick={() => {
              setRegister(!register);
              setMfa(false);
              setCode("");
            }}
          >
            {register
              ? "Already have an account? Sign in"
              : "New here? Create an account"}
          </button>
          {config.data?.demo_mode && (
            <div className="demo-entry">
              <strong>Take a look around.</strong>
              <p>
                A dedicated workspace with fictional clients and safe sample
                activity.
              </p>
              <Button
                disabled={busy}
                onClick={() =>
                  run(
                    () =>
                      post("/auth/login", {
                        email: "sarah@realty.example.com",
                        password: "RealtyAI-demo-2026!",
                      }),
                    "Demo workspace opened.",
                  )
                }
              >
                Explore demo workspace <ArrowRight size={17} />
              </Button>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

function Shell({ session }: { session: Session }) {
  const [mobile, setMobile] = useState(false);
  const [narrow, setNarrow] = useState(
    () => matchMedia("(max-width: 760px)").matches,
  );
  const navigation = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const [palette, setPalette] = useState(false);
  const [search, setSearch] = useState("");
  const [orgMenu, setOrgMenu] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const client = useQueryClient();
  const { run } = useAction();
  const organizations = useApi<{
    items: { id: string; name: string; role: string }[];
  }>("/account/organizations", orgMenu);
  useEffect(() => {
    const media = matchMedia("(max-width: 760px)");
    const changed = () => setNarrow(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  useEffect(() => {
    if (!mobile || !narrow) return;
    const controls = () =>
      Array.from(
        navigation.current?.querySelectorAll<HTMLElement>("a, button") || [],
      ).filter((element) => element.getClientRects().length);
    controls()[0]?.focus();
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobile(false);
      if (event.key === "Tab") {
        const items = controls();
        const first = items[0],
          last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", keyboard);
    const trigger = menuButton.current;
    return () => {
      document.removeEventListener("keydown", keyboard);
      trigger?.focus();
    };
  }, [mobile, narrow]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPalette((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const active =
    nav
      .flatMap((n) => [...n.items])
      .find((n) => n[1] === location.pathname)?.[0] || "Workspace";
  return (
    <SessionContext.Provider value={session}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="app-shell">
        <aside
          ref={navigation}
          id="workspace-navigation"
          className={`sidebar ${mobile ? "open" : ""}`}
          inert={narrow && !mobile}
          role={narrow && mobile ? "dialog" : undefined}
          aria-modal={narrow && mobile ? true : undefined}
          aria-label="Workspace navigation"
        >
          <div className="brand-row">
            <Link to="/" className="brand">
              <span className="brand-icon">
                <House size={21} />
              </span>
              realty<span>ai</span>
            </Link>
            <button
              className="icon-button mobile-close"
              aria-label="Close navigation"
              onClick={() => setMobile(false)}
            >
              <X size={20} />
            </button>
          </div>
          <button className="workspace-picker" onClick={() => setOrgMenu(true)}>
            <span className="workspace-monogram">N</span>
            <span>
              <strong>{session.organization.name}</strong>
              <small>
                {session.organization.is_demo
                  ? "Demo workspace"
                  : "Your workspace"}
              </small>
            </span>
            <ChevronsUpDown size={16} />
          </button>
          <nav aria-label="Main navigation">
            {nav.map((group) => (
              <div className="nav-group" key={group.label}>
                <div className="nav-label">{group.label}</div>
                {group.items.map(([name, path, Icon]) => (
                  <NavLink
                    key={path}
                    to={path}
                    end={path === "/"}
                    onClick={() => setMobile(false)}
                  >
                    <Icon size={18} />
                    <span>{name}</span>
                    {path === "/actions" && <span className="nav-new">AI</span>}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <NavLink to="/settings" onClick={() => setMobile(false)}>
              <Settings2 size={18} /> Settings
            </NavLink>
            <NavLink to="/billing" onClick={() => setMobile(false)}>
              <CreditCard size={18} /> Billing
            </NavLink>
            <div className="sidebar-person">
              <Avatar name={session.user.name} />
              <div>
                <strong>{session.user.name}</strong>
                <small>{session.role}</small>
              </div>
              <button
                className="icon-button"
                aria-label="Sign out"
                onClick={async () => {
                  await api("/auth/logout", { method: "POST" });
                  client.clear();
                  navigate("/");
                }}
              >
                <LogOut size={17} />
              </button>
            </div>
          </div>
        </aside>
        <div className="main-shell" inert={narrow && mobile}>
          <header className="topbar">
            <div className="topbar-left">
              <button
                className="icon-button mobile-menu"
                ref={menuButton}
                aria-label="Open navigation"
                aria-controls="workspace-navigation"
                aria-expanded={mobile}
                onClick={() => setMobile(true)}
              >
                <Menu size={21} />
              </button>
              <span className="breadcrumb">
                Workspace <span>/</span> <strong>{active}</strong>
              </span>
            </div>
            <div className="topbar-right">
              <button
                className="command-trigger"
                aria-label="Search or ask anything"
                onClick={() => setPalette(true)}
              >
                <Search size={17} />
                <span>Search or ask anything</span>
                <kbd>⌘ K</kbd>
              </button>
              <Link
                to="/notifications"
                className="icon-button"
                aria-label="Notifications"
              >
                <Bell size={20} />
              </Link>
              <Link
                to="/settings"
                className="icon-button"
                aria-label="Help and settings"
              >
                <CircleHelp size={20} />
              </Link>
              <Avatar name={session.user.name} size="small" />
            </div>
          </header>
          {session.organization.is_demo && (
            <div className="demo-banner">
              <span>
                <span className="status-dot" />
                Demo workspace · Fictional data. External sending is disabled.
              </span>
              <Link to="/settings">
                Connection settings <ArrowRight size={13} />
              </Link>
            </div>
          )}
          <main id="main" className="main-content">
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/contacts" element={<Contacts />} />
                <Route path="/leads" element={<Contacts kind="lead" />} />
                <Route path="/buyers" element={<Contacts kind="buyer" />} />
                <Route path="/sellers" element={<Contacts kind="seller" />} />
                <Route path="/contacts/:id" element={<Profile />} />
                {[
                  "command",
                  "inbox",
                  "properties",
                  "deals",
                  "tasks",
                  "calendar",
                  "actions",
                  "documents",
                  "analytics",
                  "notifications",
                ].map((path) => (
                  <Route
                    key={path}
                    path={"/" + path}
                    element={<WorkPages page={path} />}
                  />
                ))}
                {["settings", "billing", "workflows"].map((path) => (
                  <Route
                    key={path}
                    path={"/" + path}
                    element={<SettingsPages page={path} />}
                  />
                ))}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </main>
          <footer className="workspace-footer">
            <span>Room for the relationships that matter.</span>
            <span>
              <Sparkles size={13} /> RealtyAI
            </span>
          </footer>
        </div>
      </div>
      {palette && (
        <Modal
          title="Where would you like to go?"
          onClose={() => setPalette(false)}
        >
          <label className="palette-search">
            <Command size={21} />
            <input
              autoFocus
              placeholder="Search pages or ask about your business…"
              aria-label="Search pages or ask about your business"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <div className="palette-results">
            {nav
              .flatMap((g) => [...g.items])
              .filter(([name]) =>
                name.toLowerCase().includes(search.toLowerCase()),
              )
              .map(([name, path, Icon]) => (
                <button
                  key={path}
                  onClick={() => {
                    navigate(path);
                    setPalette(false);
                  }}
                >
                  <Icon size={19} />
                  {name}
                  <ArrowRight size={15} />
                </button>
              ))}
            {search && (
              <button
                onClick={() => {
                  navigate("/command?q=" + encodeURIComponent(search));
                  setPalette(false);
                }}
              >
                <Sparkles size={19} />
                Ask “{search}”<ArrowRight size={15} />
              </button>
            )}
          </div>
        </Modal>
      )}
      {orgMenu && (
        <Modal title="Your organizations" onClose={() => setOrgMenu(false)}>
          {organizations.data?.items.map((org) => (
            <button
              className="org-option"
              key={org.id}
              onClick={async () => {
                await run(
                  () => post(`/account/organizations/${org.id}/switch`),
                  "Workspace switched.",
                );
                client.clear();
                setOrgMenu(false);
                navigate("/");
              }}
            >
              <Building2 size={20} />
              <span>
                {org.name}
                <small>{org.role}</small>
              </span>
              {org.id === session.organization.id ? (
                <Badge tone="green">Current</Badge>
              ) : (
                <ChevronDown size={15} />
              )}
            </button>
          ))}
        </Modal>
      )}
    </SessionContext.Provider>
  );
}

export default function App() {
  const session = useApi<Session>("/auth/me");
  if (window.location.pathname === "/account-access") return <AccountAccess />;
  if (session.isLoading) return <Loading />;
  if (
    session.error &&
    !(session.error instanceof ApiError && session.error.status === 401)
  )
    return <ErrorState error={session.error} retry={() => session.refetch()} />;
  if (!session.data) return <AuthScreen />;
  if (
    session.data.require_email_verification &&
    !session.data.user.email_verified_at
  )
    return <VerificationRequired email={session.data.user.email} />;
  return <Shell session={session.data} />;
}
