import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Inbox,
  Mail,
  RefreshCw,
  Send,
  Sparkles,
} from "lucide-react";
import { useSession } from "../App";
import { date, post, useApi, words } from "../api";
import {
  ActionCard,
  Avatar,
  Badge,
  Button,
  Empty,
  ErrorState,
  Loading,
  PageTitle,
  Pager,
  SearchBox,
  useAction,
  useToast,
} from "../components";
import type { Action, Communication, Contact, Page, Profile } from "../types";

export function ActionsPage() {
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(1);
  const query = useApi<Page<Action>>(
    `/actions?page=${page}${status ? "&status=" + status : ""}`,
  );
  const session = useSession();
  return (
    <>
      <PageTitle
        eyebrow="INTELLIGENCE, WITH YOUR APPROVAL"
        title="Your action center"
        description="Thoughtful suggestions. Clear evidence. You make the call."
      />
      <div className="list-toolbar action-toolbar">
        <div className="tabs">
          {[
            ["pending", "To review"],
            ["approved", "Queued"],
            ["failed", "Needs review"],
            ["uncertain", "Verify delivery"],
            ["succeeded", "Completed"],
            ["", "All activity"],
          ].map(([value, label]) => (
            <button
              className={status === value ? "active" : ""}
              key={label}
              onClick={() => {
                setStatus(value);
                setPage(1);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <Button onClick={() => query.refetch()}>
          <RefreshCw size={16} />
          Refresh
        </Button>
      </div>
      {query.isLoading ? (
        <Loading />
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : query.data?.items.length ? (
        <>
          <div className="action-list">
            {query.data.items.map((a) => (
              <ActionCard
                key={a.id}
                action={a}
                canApprove={["owner", "admin", "agent"].includes(session.role)}
              />
            ))}
          </div>
          <Pager page={page} total={query.data.total} onPage={setPage} />
        </>
      ) : (
        <Empty
          title="A clear action inbox"
          body="Analyze a conversation or prepare a follow-up to see suggestions here."
          action={
            <Link className="button primary" to="/inbox">
              Open inbox <ArrowRight size={17} />
            </Link>
          }
        />
      )}
    </>
  );
}
interface CommandAnswer {
  answer: string;
  records: Contact[];
  source_ids: string[];
  mode: string;
  context?: Profile;
}
export function CommandPage() {
  const [params] = useSearchParams();
  const [question, setQuestion] = useState(params.get("q") || "");
  const [answer, setAnswer] = useState<CommandAnswer | null>(null);
  const [asked, setAsked] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const initial = useRef(false);
  async function ask(q: string) {
    if (!q.trim() || busy) return;
    setBusy(true);
    setAsked(q);
    try {
      setAnswer(await post<CommandAnswer>("/command", { question: q }));
    } catch (e) {
      toast(
        e instanceof Error ? e.message : "Could not answer the question.",
        true,
      );
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    const q = params.get("q");
    if (q && !initial.current) {
      initial.current = true;
      void ask(q);
    }
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void ask(question);
  };
  return (
    <div className="command-page">
      <PageTitle
        eyebrow="YOUR AI COMMAND CENTER"
        title="A clearer picture starts here."
        description="Ask about your relationships, your calendar, or your next move."
      />
      <div className="command-suggestions">
        {[
          "What needs my attention today?",
          "Who are my hottest leads?",
          "Show buyers under $700k",
          "Who hasn't been contacted in 7 days?",
        ].map((q) => (
          <button
            disabled={busy}
            key={q}
            onClick={() => {
              setQuestion(q);
              void ask(q);
            }}
          >
            <Sparkles size={16} />
            {q}
            <ArrowRight size={15} />
          </button>
        ))}
      </div>
      {asked && (
        <div className="conversation-question">
          <span>You</span>
          <p>{asked}</p>
        </div>
      )}
      {busy ? (
        <Loading />
      ) : answer ? (
        <section className="command-answer">
          <div className="assistant-label">
            <span className="assistant-icon">
              <Sparkles size={19} />
            </span>
            <strong>RealtyAI</strong>
            <Badge tone={answer.mode === "ai_generated" ? "amber" : "green"}>
              {answer.mode === "ai_generated"
                ? "AI-generated · Review sources"
                : "From your workspace"}
            </Badge>
          </div>
          <p className="answer-text">{answer.answer}</p>
          {answer.records?.length > 0 && (
            <div className="answer-records">
              {answer.records.map((record) => (
                <Link
                  to={record.name ? "/contacts/" + record.id : "/tasks"}
                  key={record.id}
                >
                  <Avatar name={record.name || "Task"} />
                  <div>
                    <strong>
                      {record.name ||
                        ("title" in record ? String(record.title) : "Record")}
                    </strong>
                    <span>
                      {record.kind ? words(record.kind) : "Task"}{" "}
                      {record.email && "· " + record.email}
                    </span>
                  </div>
                  <ArrowRight size={17} />
                </Link>
              ))}
            </div>
          )}
          {answer.context?.missing && (
            <div className="answer-context">
              <h3>Questions for the next conversation</h3>
              <ul>
                {answer.context.missing.map((m) => (
                  <li key={m}>Confirm {words(m).toLowerCase()}.</li>
                ))}
              </ul>
              <Link
                className="button secondary"
                to={"/contacts/" + answer.context.contact.id}
              >
                Open full meeting preparation <ArrowRight size={16} />
              </Link>
            </div>
          )}
          {answer.source_ids.length > 0 && (
            <small>
              {answer.source_ids.length} source records · Results stay within
              your organization
            </small>
          )}
        </section>
      ) : (
        <div className="command-welcome">
          <Sparkles size={36} />
          <h2>Your business already holds the answers.</h2>
          <p>Let's bring the useful details into focus.</p>
        </div>
      )}
      <form className="command-input" onSubmit={submit}>
        <Sparkles size={23} />
        <label className="sr-only" htmlFor="command-question">
          Ask about your business
        </label>
        <input
          id="command-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about your business…"
          maxLength={2000}
        />
        <Button
          variant="primary"
          type="submit"
          disabled={busy || !question.trim()}
          aria-label="Send question"
        >
          <Send size={18} />
        </Button>
      </form>
      <p className="command-note">
        Queries use your records. Open-ended AI requires a configured provider.
        No action is executed by a question.
      </p>
    </div>
  );
}
export function InboxPage() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Communication | null>(null);
  const query = useApi<Page<Communication>>(
    `/inbox?page=${page}&q=${encodeURIComponent(q)}`,
  );
  const { busy, run } = useAction();
  const message =
    query.data?.items.find((m) => m.id === selected?.id) ||
    selected ||
    query.data?.items[0];
  return (
    <>
      <PageTitle
        eyebrow="EVERY CONVERSATION COUNTS"
        title="Your relationship inbox"
        description="Find the context. Catch a commitment. Prepare the next conversation."
        action={
          <Button
            disabled={busy}
            onClick={() =>
              run(
                () => post("/integrations/google/sync?resource=gmail"),
                "Gmail sync queued.",
              )
            }
          >
            <RefreshCw size={17} />
            Sync Gmail
          </Button>
        }
      />
      <div className="section-card inbox-card">
        <div className="list-toolbar">
          <SearchBox
            value={q}
            onChange={(v) => {
              setQ(v);
              setPage(1);
            }}
            placeholder="Search email subjects"
          />
          <Link to="/settings" className="text-button">
            Manage connection <ArrowRight size={15} />
          </Link>
        </div>
        {query.isLoading ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : query.data?.items.length ? (
          <div className="inbox-layout">
            <div className="message-list">
              {query.data.items.map((m) => (
                <button
                  className={`message-preview ${m.id === message?.id ? "selected" : ""}`}
                  key={m.id}
                  onClick={() => setSelected(m)}
                >
                  <div>
                    <strong>{m.sender.split("@")[0]}</strong>
                    <small>{date(m.received_at)}</small>
                  </div>
                  <h3>{m.subject}</h3>
                  <p>{m.body.slice(0, 100)}</p>
                  <span>
                    {m.analyzed ? (
                      <Badge tone="green">Analyzed</Badge>
                    ) : (
                      <Badge>Ready to analyze</Badge>
                    )}
                  </span>
                </button>
              ))}
            </div>
            {message && (
              <article className="message-detail">
                <div className="message-detail-heading">
                  <div className="action-meta">
                    <Badge tone="blue">
                      <Mail size={12} />
                      Email
                    </Badge>
                    <Badge>{words(message.direction)}</Badge>
                  </div>
                  <h2>{message.subject}</h2>
                  <div className="sender-row">
                    <Avatar name={message.sender} />
                    <div>
                      <strong>{message.sender}</strong>
                      <small>
                        To {message.recipient} · {date(message.received_at)}
                      </small>
                    </div>
                  </div>
                </div>
                <div className="message-body pre-wrap">{message.body}</div>
                {message.summary && (
                  <div className="email-summary">
                    <Sparkles size={18} />
                    <div>
                      <strong>Internal summary</strong>
                      <p>{message.summary}</p>
                      <small>
                        Generated analysis · Verify against the original message
                      </small>
                    </div>
                  </div>
                )}
                <div className="message-actions">
                  <Button
                    variant="primary"
                    disabled={busy || message.analyzed}
                    onClick={() =>
                      run(
                        () => post(`/inbox/${message.id}/analyze`),
                        "Analysis complete. Review extracted suggestions in AI actions.",
                      )
                    }
                  >
                    <Sparkles size={16} />
                    {message.analyzed
                      ? "Analysis complete"
                      : "Analyze conversation"}
                  </Button>
                  {message.contact_id && (
                    <Link
                      className="button secondary"
                      to={"/contacts/" + message.contact_id}
                    >
                      Client profile <ArrowRight size={16} />
                    </Link>
                  )}
                </div>
                <p className="help-text">
                  Email content is treated as untrusted data. Extracted facts
                  require review before changing a client profile.
                </p>
              </article>
            )}
          </div>
        ) : (
          <Empty
            title="Your conversations will feel at home here"
            body="Connect Google in Settings, then sync relevant Gmail messages."
            action={
              <Link className="button primary" to="/settings">
                <Inbox size={17} />
                Connect Google
              </Link>
            }
          />
        )}
      </div>
      {query.data && (
        <Pager page={page} total={query.data.total} onPage={setPage} />
      )}
    </>
  );
}
