import {
  ArrowDownRight,
  ArrowRight,
  CalendarDays,
  CheckCheck,
  Clock3,
  Plus,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useState, type FormEvent } from "react";
import { useApi, money, time } from "./api";
import {
  ActionCard,
  Avatar,
  Badge,
  Empty,
  ErrorState,
  Loading,
} from "./components";
import { useSession } from "./App";
import type { Briefing } from "./types";

export default function Dashboard() {
  const query = useApi<Briefing>("/briefing");
  const session = useSession();
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  if (query.isLoading) return <Loading />;
  if (query.error)
    return <ErrorState error={query.error} retry={() => query.refetch()} />;
  if (!query.data) return null;
  const data = query.data;
  const ask = (e: FormEvent) => {
    e.preventDefault();
    if (question.trim()) navigate("/command?q=" + encodeURIComponent(question));
  };
  return (
    <div className="dashboard">
      <div className="dashboard-heading">
        <div className="eyebrow">
          {new Date().toLocaleDateString("en-US", {
            weekday: "long",
            month: "long",
            day: "numeric",
          })}
        </div>
        <div className="greeting-row">
          <div>
            <h1>
              Good{" "}
              {new Date().getHours() < 12
                ? "morning"
                : new Date().getHours() < 18
                  ? "afternoon"
                  : "evening"}
              , {session.user.name.split(" ")[0]}
              <span className="greeting-dot">.</span>
            </h1>
            <p>Here's where a little attention can make a big difference.</p>
          </div>
          <Link to="/contacts" className="button secondary">
            <Plus size={17} /> Add a contact
          </Link>
        </div>
      </div>
      <section className="briefing-banner">
        <div className="briefing-symbol">
          <Sparkles size={27} />
        </div>
        <div>
          <div className="eyebrow">YOUR DAILY BRIEFING</div>
          <h2>
            {data.pending_actions
              ? "A few next steps. More room to connect."
              : "A clear workspace. A fresh start."}
          </h2>
          <p>
            {data.pending_actions} suggestions ready for your review,{" "}
            {data.followups.length} relationships to follow up, and{" "}
            {data.appointments.length} appointments today.
          </p>
        </div>
        <Link className="button light" to="/actions">
          Review priorities <ArrowRight size={17} />
        </Link>
      </section>
      <section className="stats-grid" aria-label="Workspace at a glance">
        {[
          {
            label: "Active relationships",
            value: String(data.contacts),
            hint: "People in your workspace",
            icon: Users,
            path: "/contacts",
          },
          {
            label: "Active pipeline",
            value: money(data.pipeline_value),
            hint: `Across ${data.active_deals} open deals`,
            icon: TrendingUp,
            path: "/deals",
          },
          {
            label: "Ready for review",
            value: String(data.pending_actions).padStart(2, "0"),
            hint: "Your judgment makes the difference",
            icon: Sparkles,
            path: "/actions",
          },
          {
            label: "Overdue tasks",
            value: String(data.overdue_tasks).padStart(2, "0"),
            hint: data.overdue_tasks
              ? "A good place to start today"
              : "You’re all caught up",
            icon: CheckCheck,
            path: "/tasks",
          },
        ].map(({ label, value, hint, icon: Icon, path }) => (
          <Link to={path} className="stat" key={label}>
            <div className="stat-label">
              {label}
              <Icon size={18} />
            </div>
            <strong>{value}</strong>
            <small>{hint}</small>
          </Link>
        ))}
      </section>
      <div className="dashboard-columns">
        <div className="dashboard-primary">
          <section className="section-card priorities">
            <div className="section-heading">
              <div>
                <h2>
                  <Sparkles size={20} /> Your next best moves{" "}
                  <Badge tone="green">{data.pending_actions}</Badge>
                </h2>
                <p>Prepared by your assistant. Decided by you.</p>
              </div>
              <Link to="/actions">
                View all <ArrowRight size={15} />
              </Link>
            </div>
            {data.actions.length ? (
              data.actions
                .slice(0, 3)
                .map((a) => (
                  <ActionCard
                    key={a.id}
                    action={a}
                    compact
                    canApprove={["owner", "admin", "agent"].includes(
                      session.role,
                    )}
                  />
                ))
            ) : (
              <Empty
                title="Nothing waiting on you"
                body="New suggestions will appear as your workspace changes."
              />
            )}
          </section>
          <section className="section-card relationships">
            <div className="section-heading">
              <div>
                <h2>Keep the conversation going</h2>
                <p>A thoughtful check-in can move a relationship forward.</p>
              </div>
              <Link to="/contacts">
                All contacts <ArrowRight size={15} />
              </Link>
            </div>
            {data.followups.length ? (
              data.followups.slice(0, 3).map((contact) => (
                <Link
                  to={"/contacts/" + contact.id}
                  className="relationship-row"
                  key={contact.id}
                >
                  <Avatar name={contact.name} />
                  <div>
                    <strong>{contact.name}</strong>
                    <span>
                      {contact.kind} ·{" "}
                      {contact.last_contact_at
                        ? "Last conversation " +
                          Math.floor(
                            (Date.now() -
                              new Date(
                                contact.last_contact_at + "Z",
                              ).getTime()) /
                              86400000,
                          ) +
                          " days ago"
                        : "No conversation recorded"}
                    </span>
                  </div>
                  <Badge tone={contact.score >= 70 ? "green" : "neutral"}>
                    {contact.score >= 70 ? "High intent" : "Check in"}
                  </Badge>
                  <ArrowRight size={17} />
                </Link>
              ))
            ) : (
              <Empty
                title="Your conversations are current"
                body="Clients needing a follow-up will appear here."
              />
            )}
          </section>
        </div>
        <aside className="dashboard-aside">
          <section className="section-card agenda">
            <div className="section-heading">
              <h2>
                On your calendar <CalendarDays size={19} />
              </h2>
              <Link to="/calendar" aria-label="View calendar">
                <ArrowRight size={17} />
              </Link>
            </div>
            <div className="agenda-date">
              <strong>{new Date().getDate()}</strong>
              <div>
                {new Date().toLocaleDateString("en-US", { weekday: "long" })}
                <small>
                  {new Date().toLocaleDateString("en-US", {
                    month: "long",
                    year: "numeric",
                  })}
                </small>
              </div>
              <Badge>Today</Badge>
            </div>
            {data.appointments.length ? (
              data.appointments.map((a, i) => (
                <Link
                  to={a.contact_id ? "/contacts/" + a.contact_id : "/calendar"}
                  className="agenda-item"
                  key={a.id}
                >
                  <span className="agenda-line" />
                  <div className="agenda-time">{time(a.start_at)}</div>
                  <strong>{a.title}</strong>
                  <span>{a.location || "Location not set"}</span>
                  <small>
                    <Clock3 size={13} />
                    {Math.round(
                      (new Date(a.end_at).getTime() -
                        new Date(a.start_at).getTime()) /
                        60000,
                    )}{" "}
                    min{" "}
                    {i === 0 && (
                      <span className="prepare-label">
                        Prepare <ArrowRight size={13} />
                      </span>
                    )}
                  </small>
                </Link>
              ))
            ) : (
              <Empty
                title="A little breathing room"
                body="No appointments are recorded for today."
              />
            )}
            <Link to="/calendar" className="agenda-footer">
              Open calendar <ArrowRight size={15} />
            </Link>
          </section>
          <section className="ask-card">
            <div className="ask-icon">
              <Sparkles size={22} />
            </div>
            <h3>Your business, in a conversation.</h3>
            <p>
              Find a client, prepare for a meeting, or see what needs your
              attention.
            </p>
            <form onSubmit={ask}>
              <label className="sr-only" htmlFor="dashboard-question">
                Ask your assistant
              </label>
              <input
                id="dashboard-question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="What should I focus on?"
              />
              <button aria-label="Ask question" type="submit">
                <ArrowRight size={19} />
              </button>
            </form>
            <div className="ask-suggestion">
              <ArrowDownRight size={15} />
              <button
                onClick={() =>
                  navigate("/command?q=Who%20are%20my%20hottest%20leads%3F")
                }
              >
                Who are my hottest leads?
              </button>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
