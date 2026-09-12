import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileText,
  Mail,
  MapPin,
  Phone,
  Plus,
  Sparkles,
} from "lucide-react";
import { date, money, post, put, useApi, words } from "./api";
import {
  Avatar,
  Badge,
  Button,
  Empty,
  ErrorState,
  Field,
  Loading,
  Modal,
  Submit,
  useAction,
} from "./components";
import type { Profile as ProfileData } from "./types";

export default function Profile() {
  const { id } = useParams();
  const query = useApi<ProfileData>(`/contacts/${id}/profile`);
  const [modal, setModal] = useState<"preferences" | "note" | "contact" | null>(
    null,
  );
  const [tab, setTab] = useState("timeline");
  const { busy, run } = useAction();
  if (query.isLoading) return <Loading />;
  if (query.error) return <ErrorState error={query.error} />;
  if (!query.data) return null;
  const p = query.data,
    c = p.contact;
  const savePreferences = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.currentTarget));
    const body = {
      ...d,
      budget_min: d.budget_min ? Number(d.budget_min) : null,
      budget_max: d.budget_max ? Number(d.budget_max) : null,
      bedrooms: d.bedrooms ? Number(d.bedrooms) : null,
      bathrooms: d.bathrooms ? Number(d.bathrooms) : null,
      location: d.location || null,
      timeline: d.timeline || null,
      financing: d.financing || null,
      property_type: d.property_type || null,
      features: String(d.features)
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean),
    };
    const result = await run(
      () => put(`/contacts/${id}/preferences`, body),
      "Preferences saved as confirmed information.",
    );
    if (result) setModal(null);
  };
  const saveNote = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const result = await run(
      () =>
        post(
          `/contacts/${id}/notes`,
          Object.fromEntries(new FormData(e.currentTarget)),
        ),
      "Activity added to the timeline.",
    );
    if (result) setModal(null);
  };
  const saveContact = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.currentTarget));
    const result = await run(
      () =>
        put(`/crm/contacts/${id}`, {
          ...d,
          email: d.email || null,
          phone: d.phone || null,
          archived: false,
        }),
      "Contact updated.",
    );
    if (result) setModal(null);
  };
  return (
    <>
      <Link to="/contacts" className="back-link">
        <ArrowLeft size={16} />
        All contacts
      </Link>
      <div className="profile-heading">
        <Avatar name={c.name} size="large" />
        <div>
          <div className="action-meta">
            <Badge tone="green">{words(c.kind)}</Badge>
            <Badge>{words(c.stage)}</Badge>
          </div>
          <h1>{c.name}</h1>
          <div className="contact-methods">
            {c.email && (
              <a href={"mailto:" + c.email}>
                <Mail size={15} />
                {c.email}
              </a>
            )}
            {c.phone && (
              <a href={"tel:" + c.phone}>
                <Phone size={15} />
                {c.phone}
              </a>
            )}
          </div>
        </div>
        <div className="profile-actions">
          <Button onClick={() => setModal("contact")}>Edit contact</Button>
          <Button
            variant="primary"
            disabled={busy}
            onClick={() =>
              run(
                () => post(`/contacts/${id}/followup`),
                "Follow-up draft added to AI actions.",
              )
            }
          >
            <Sparkles size={17} />
            Draft follow-up
          </Button>
        </div>
      </div>
      <div className="profile-layout">
        <aside>
          <section className="section-card profile-criteria">
            <div className="section-heading">
              <h2>Buying preferences</h2>
              <button
                className="text-button"
                onClick={() => setModal("preferences")}
              >
                Edit
              </button>
            </div>
            <div className="criteria-list">
              {[
                [
                  "Budget",
                  p.preferences?.budget_max
                    ? `${money(p.preferences.budget_min)} – ${money(p.preferences.budget_max)}`
                    : "Not recorded",
                ],
                ["Location", p.preferences?.location],
                ["Bedrooms", p.preferences?.bedrooms],
                ["Bathrooms", p.preferences?.bathrooms],
                ["Timeline", p.preferences?.timeline],
                ["Financing", p.preferences?.financing],
              ].map(([label, value]) => (
                <div key={String(label)}>
                  <span>{label}</span>
                  <strong>{value || "Not recorded"}</strong>
                </div>
              ))}
            </div>
            <div className="criteria-features">
              {p.preferences?.features.map((f) => (
                <Badge key={f}>{f}</Badge>
              ))}
            </div>
            <small className="verified-line">
              <CheckCircle2 size={14} />
              Confirmed fields · View evidence below
            </small>
          </section>
          <section className="missing-card">
            <Sparkles size={21} />
            <h3>A little more context</h3>
            {p.missing.length ? (
              <>
                <p>
                  {p.missing.map(words).join(", ")}{" "}
                  {p.missing.length > 1 ? "have" : "has"} not been recorded. Ask
                  before assuming.
                </p>
                <button
                  className="text-button"
                  onClick={() => setModal("preferences")}
                >
                  Add what you know <ArrowRight size={15} />
                </button>
              </>
            ) : (
              <p>
                Core preferences have been recorded. Confirm they are still
                current at your next conversation.
              </p>
            )}
          </section>
          <section className="section-card intent-card">
            <h3>Recorded intent</h3>
            <strong>
              {c.score}
              <span>/100</span>
            </strong>
            <p>{c.score_reason}</p>
            <Badge>Assessment · Not a verified fact</Badge>
          </section>
        </aside>
        <div>
          <div
            className="tabs"
            role="tablist"
            aria-label="Client profile sections"
          >
            {["timeline", "preparation", "properties", "evidence"].map((t) => (
              <button
                role="tab"
                aria-selected={tab === t}
                className={tab === t ? "active" : ""}
                key={t}
                onClick={() => setTab(t)}
              >
                {words(t)}
              </button>
            ))}
          </div>
          {tab === "timeline" && (
            <section className="section-card timeline-card">
              <div className="section-heading">
                <div>
                  <h2>The relationship, in context</h2>
                  <p>Communication, notes and completed actions.</p>
                </div>
                <Button onClick={() => setModal("note")}>
                  <Plus size={16} />
                  Log activity
                </Button>
              </div>
              {p.activities.length ? (
                p.activities.map((a) => (
                  <article className="timeline-event" key={a.id}>
                    <span className="timeline-icon">
                      {a.kind === "email" ? (
                        <Mail size={17} />
                      ) : a.kind === "ai_action" ? (
                        <Sparkles size={17} />
                      ) : (
                        <FileText size={17} />
                      )}
                    </span>
                    <div>
                      <div className="timeline-meta">
                        <Badge>{words(a.kind)}</Badge>
                        <span>{date(a.created_at)}</span>
                      </div>
                      <h3>{a.title}</h3>
                      <p className="pre-wrap">{a.body}</p>
                    </div>
                  </article>
                ))
              ) : (
                <Empty
                  title="The story starts here"
                  body="Add a note or sync communication to begin this client's timeline."
                />
              )}
            </section>
          )}
          {tab === "preparation" && (
            <section className="section-card prep-card">
              <div className="section-heading">
                <h2>
                  <Sparkles size={19} />
                  Ready for your next conversation
                </h2>
                <Badge tone="green">From your records</Badge>
              </div>
              <h3>Open questions</h3>
              {p.missing.length ? (
                <ul>
                  {p.missing.map((f) => (
                    <li key={f}>
                      Confirm {words(f).toLowerCase()} with{" "}
                      {c.name.split(" ")[0]}.
                    </li>
                  ))}
                </ul>
              ) : (
                <p>
                  Confirm that the recorded criteria still reflect the client's
                  plans.
                </p>
              )}
              <h3>Outstanding tasks</h3>
              {p.tasks
                .filter((t) => t.status === "open")
                .map((t) => (
                  <div className="prep-item" key={t.id}>
                    <Clock3 size={17} />
                    {t.title}
                    <Badge>{date(t.due_at)}</Badge>
                  </div>
                ))}
              {!p.tasks.some((t) => t.status === "open") && (
                <p>No open tasks recorded.</p>
              )}
              <h3>Recent communication</h3>
              {p.communications.slice(0, 3).map((m) => (
                <article className="prep-email" key={m.id}>
                  <strong>{m.subject}</strong>
                  <small>{date(m.received_at)}</small>
                  <p>{m.summary || m.body}</p>
                </article>
              ))}
              <h3>Commitments to review</h3>
              {p.commitments.length ? (
                p.commitments.map((v) => (
                  <p key={v.id}>
                    {v.title} <Badge>{v.status}</Badge>
                  </p>
                ))
              ) : (
                <p>No commitments have been extracted.</p>
              )}
            </section>
          )}
          {tab === "properties" && (
            <section className="match-list">
              {p.matches.length ? (
                p.matches.map((m) => (
                  <article
                    className="section-card match-card"
                    key={m.property.id}
                  >
                    <div className="match-heading">
                      <div>
                        <h3>{m.property.address}</h3>
                        <span>
                          <MapPin size={14} />
                          {m.property.location}
                        </span>
                      </div>
                      <strong>
                        {m.score === null ? "Unknown" : m.score + "%"}
                        <small>criteria match</small>
                      </strong>
                    </div>
                    <p>
                      {money(m.property.price)} · {m.property.bedrooms} beds ·{" "}
                      {m.property.bathrooms} baths
                    </p>
                    <div className="match-factors">
                      {m.factors.map((f) => (
                        <Badge
                          key={f.label}
                          tone={
                            f.state === "match"
                              ? "green"
                              : f.state === "conflict"
                                ? "amber"
                                : "neutral"
                          }
                        >
                          {f.label}: {f.state}
                        </Badge>
                      ))}
                    </div>
                    <small>
                      {m.coverage}. {m.method}
                    </small>
                  </article>
                ))
              ) : (
                <Empty
                  title="No properties to compare yet"
                  body="Add property records to find matches against confirmed preferences."
                />
              )}
            </section>
          )}
          {tab === "evidence" && (
            <section className="section-card evidence-card">
              <div className="section-heading">
                <h2>Facts with a source</h2>
              </div>
              <p className="help-text">
                Extracted information remains a suggestion until reviewed. A
                confidence score is an assessment, not proof.
              </p>
              {p.facts.map((f) => (
                <article className="fact-row" key={f.id}>
                  <div>
                    <strong>{words(f.field)}</strong>
                    <Badge tone={f.state === "confirmed" ? "green" : "amber"}>
                      {words(f.state)}
                    </Badge>
                  </div>
                  <p>
                    {typeof f.value === "object"
                      ? JSON.stringify(f.value)
                      : String(f.value)}
                  </p>
                  {f.quote && <blockquote>{f.quote}</blockquote>}
                  <small>
                    {f.source_type} · {f.method} ·{" "}
                    {Math.round(f.confidence * 100)}% confidence ·{" "}
                    {date(f.created_at)}
                  </small>
                  <small>Source: {f.source_id || "Not recorded"}</small>
                </article>
              ))}
            </section>
          )}
        </div>
      </div>
      {modal === "preferences" && (
        <Modal
          title="Update buying preferences"
          onClose={() => setModal(null)}
          wide
        >
          <form onSubmit={savePreferences}>
            <div className="form-grid">
              {[
                ["budget_min", "Minimum budget"],
                ["budget_max", "Maximum budget"],
                ["bedrooms", "Bedrooms"],
                ["bathrooms", "Bathrooms"],
                ["location", "Preferred location"],
                ["timeline", "Timeline"],
                ["financing", "Financing"],
              ].map(([name, label]) => (
                <Field key={name} label={label}>
                  <input
                    name={name}
                    type={
                      [
                        "budget_min",
                        "budget_max",
                        "bedrooms",
                        "bathrooms",
                      ].includes(name)
                        ? "number"
                        : "text"
                    }
                    min="0"
                    step={name === "bathrooms" ? ".5" : "1"}
                    defaultValue={String(
                      p.preferences?.[name as keyof typeof p.preferences] || "",
                    )}
                  />
                </Field>
              ))}
              <Field label="Property type">
                <select
                  name="property_type"
                  defaultValue={p.preferences?.property_type || ""}
                >
                  <option value="">Not recorded</option>
                  {[
                    "single_family",
                    "condo",
                    "townhouse",
                    "multi_family",
                    "land",
                  ].map((t) => (
                    <option value={t} key={t}>
                      {words(t)}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label="Features (comma separated)">
              <input
                name="features"
                defaultValue={p.preferences?.features.join(", ")}
              />
            </Field>
            <p className="help-text">
              Manual entries are recorded as confirmed information with you as
              the source.
            </p>
            <Submit busy={busy} />
          </form>
        </Modal>
      )}
      {modal === "note" && (
        <Modal title="Log relationship activity" onClose={() => setModal(null)}>
          <form onSubmit={saveNote}>
            <Field label="Activity type">
              <select name="kind">
                {[
                  "note",
                  "call",
                  "showing",
                  "feedback",
                  "offer",
                  "price_change",
                ].map((k) => (
                  <option key={k} value={k}>
                    {words(k)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Title">
              <input name="title" required maxLength={250} />
            </Field>
            <Field label="Notes">
              <textarea name="body" rows={6} maxLength={20000} />
            </Field>
            <Submit busy={busy} label="Add to timeline" />
          </form>
        </Modal>
      )}
      {modal === "contact" && (
        <Modal title="Edit contact" onClose={() => setModal(null)}>
          <form onSubmit={saveContact}>
            <Field label="Full name">
              <input name="name" required defaultValue={c.name} />
            </Field>
            <Field label="Email">
              <input name="email" type="email" defaultValue={c.email || ""} />
            </Field>
            <Field label="Phone">
              <input name="phone" defaultValue={c.phone || ""} />
            </Field>
            <div className="form-grid">
              <Field label="Relationship">
                <select name="kind" defaultValue={c.kind}>
                  {["lead", "buyer", "seller", "contact"].map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
              </Field>
              <Field label="Stage">
                <select name="stage" defaultValue={c.stage}>
                  {["new", "nurturing", "qualified", "active", "closed"].map(
                    (k) => (
                      <option key={k}>{k}</option>
                    ),
                  )}
                </select>
              </Field>
            </div>
            <Submit busy={busy} />
          </form>
        </Modal>
      )}
    </>
  );
}
