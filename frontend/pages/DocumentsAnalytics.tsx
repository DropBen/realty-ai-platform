import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  Bell,
  Check,
  Download,
  FileText,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";
import { api, date, money, post, useApi, words } from "../api";
import {
  Badge,
  Button,
  Empty,
  ErrorState,
  Field,
  Loading,
  Modal,
  PageTitle,
  Pager,
  SearchBox,
  Submit,
  useAction,
} from "../components";
import type {
  Analytics,
  Contact,
  Document,
  Notification,
  Page,
} from "../types";

export function DocumentsPage() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [upload, setUpload] = useState(false);
  const [selected, setSelected] = useState<Document | null>(null);
  const [deleting, setDeleting] = useState<Document | null>(null);
  const query = useApi<Page<Document>>(
    `/documents?page=${page}&q=${encodeURIComponent(q)}`,
  );
  const contacts = useApi<Page<Contact>>("/crm/contacts?page_size=100");
  const { busy, run } = useAction();
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (!form.get("contact_id")) form.delete("contact_id");
    const result = await run(
      () => api("/documents", { method: "POST", body: form }),
      "Document uploaded.",
    );
    if (result) setUpload(false);
  };
  return (
    <>
      <PageTitle
        eyebrow="THE DETAILS, TOGETHER"
        title="Your document library"
        description="Client files with context, permissions and a clear history."
        action={
          <Button variant="primary" onClick={() => setUpload(true)}>
            <Plus size={17} />
            Upload document
          </Button>
        }
      />
      <div className="section-card">
        <div className="list-toolbar">
          <SearchBox
            value={q}
            onChange={(v) => {
              setQ(v);
              setPage(1);
            }}
            placeholder="Search names or extracted text"
          />
          <Badge>PDF & text · up to 10 MB</Badge>
        </div>
        {query.isLoading ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : query.data?.items.length ? (
          <div className="document-list">
            {query.data.items.map((d) => (
              <article className="document-row" key={d.id}>
                <span className="document-icon">
                  <FileText size={24} />
                </span>
                <div>
                  <button
                    className="text-button document-title"
                    onClick={() => setSelected(d)}
                  >
                    {d.name}
                  </button>
                  <small>
                    {Math.ceil(d.size / 1024)} KB · {date(d.created_at)}
                  </small>
                </div>
                <Badge tone={d.status === "extracted" ? "green" : "neutral"}>
                  {words(d.status)}
                </Badge>
                <a
                  className="icon-button"
                  aria-label={"Download " + d.name}
                  href={"/api/v1/documents/" + d.id + "/download"}
                >
                  <Download size={18} />
                </a>
                <button
                  className="icon-button"
                  aria-label={"Delete " + d.name}
                  onClick={() => setDeleting(d)}
                >
                  <Trash2 size={17} />
                </button>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            title="A place for the important details"
            body="Upload a document to keep it connected to a client. Text can be searched after extraction."
          />
        )}
        {query.data && (
          <Pager page={page} total={query.data.total} onPage={setPage} />
        )}
      </div>
      {upload && (
        <Modal title="Upload a document" onClose={() => setUpload(false)}>
          <form onSubmit={submit}>
            <Field
              label="File"
              hint="PDF or UTF-8 text, maximum 10 MB. Scanned PDFs need a configured OCR provider."
            >
              <input name="file" type="file" accept=".pdf,.txt" required />
            </Field>
            <Field label="Client">
              <select name="contact_id">
                <option value="">Workspace document</option>
                {contacts.data?.items.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
            <Submit busy={busy} label="Upload document" />
          </form>
        </Modal>
      )}
      {selected && (
        <Modal title={selected.name} onClose={() => setSelected(null)}>
          <Badge>{words(selected.status)}</Badge>
          {selected.summary ? (
            <>
              <h3>AI summary · Review required</h3>
              <p className="pre-wrap">{selected.summary}</p>
            </>
          ) : (
            <p>
              No summary has been generated. Summaries require a configured AI
              provider and extracted document text.
            </p>
          )}
          <Button
            disabled={busy}
            onClick={async () => {
              const updated = await run(
                () => post<Document>(`/documents/${selected.id}/summarize`),
                "Document summary generated.",
              );
              if (updated) setSelected(updated);
            }}
          >
            <Sparkles size={17} />
            Generate summary
          </Button>
        </Modal>
      )}
      {deleting && (
        <Modal title="Delete document?" onClose={() => setDeleting(null)}>
          <p>
            “{deleting.name}” and its stored file will be permanently removed.
          </p>
          <div className="modal-actions">
            <Button onClick={() => setDeleting(null)}>Keep document</Button>
            <Button
              variant="danger"
              disabled={busy}
              onClick={async () => {
                const result = await run(
                  () => api(`/documents/${deleting.id}`, { method: "DELETE" }),
                  "Document deleted.",
                );
                if (result) setDeleting(null);
              }}
            >
              Delete document
            </Button>
          </div>
        </Modal>
      )}
    </>
  );
}
export function AnalyticsPage() {
  const query = useApi<Analytics>("/analytics");
  if (query.isLoading) return <Loading />;
  if (query.error) return <ErrorState error={query.error} />;
  const data = query.data;
  if (!data) return null;
  const max = Math.max(1, ...data.pipeline.map((s) => s.value));
  return (
    <>
      <PageTitle
        eyebrow="PERSPECTIVE FOR YOUR NEXT MOVE"
        title="See the bigger picture."
        description="A live view of your pipeline, assistant decisions and measured activity."
      />
      <div className="analytics-grid">
        <section className="section-card chart-card">
          <div className="section-heading">
            <h2>Pipeline by stage</h2>
            <Badge>Recorded deal values</Badge>
          </div>
          {data.pipeline.length ? (
            <div className="bar-chart">
              {data.pipeline.map((s) => (
                <div className="chart-row" key={s.stage}>
                  <div>
                    <span>{words(s.stage)}</span>
                    <strong>{money(s.value)}</strong>
                  </div>
                  <div className="chart-track">
                    <span
                      style={{
                        width: Math.max(2, (s.value / max) * 100) + "%",
                      }}
                    />
                  </div>
                  <small>
                    {s.count} {s.count === 1 ? "deal" : "deals"}
                  </small>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="Your pipeline will tell a story"
              body="Create deals to see their value by stage."
            />
          )}
        </section>
        <section className="section-card chart-card">
          <div className="section-heading">
            <h2>Assistant decisions</h2>
            <Sparkles size={21} />
          </div>
          {data.actions.map((a) => (
            <div className="decision-metric" key={a.status}>
              <span>
                <span className={"decision-dot " + a.status} />
                {words(a.status)}
              </span>
              <strong>{a.count}</strong>
            </div>
          ))}
          <p className="help-text">
            Your review outcomes are recorded. No model retraining occurs
            automatically.
          </p>
        </section>
        <section className="section-card usage-card">
          <div className="section-heading">
            <h2>Measured usage</h2>
            <Badge>All time</Badge>
          </div>
          {data.usage.length ? (
            <div className="usage-grid">
              {data.usage.map((u) => (
                <div key={u.metric}>
                  <strong>{u.quantity.toLocaleString()}</strong>
                  <span>{words(u.metric)}</span>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="Usage starts with activity"
              body="AI requests, processed messages, documents and workflow executions appear here as they occur."
            />
          )}
        </section>
      </div>
    </>
  );
}
export function NotificationsPage() {
  const query = useApi<Page<Notification>>("/notifications");
  const { run, busy } = useAction();
  return (
    <>
      <PageTitle
        eyebrow="IN THE LOOP"
        title="Notifications"
        description="Useful changes and things that need your attention."
      />
      <section className="section-card">
        {query.isLoading ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : query.data?.items.length ? (
          query.data.items.map((n) => (
            <article
              className={`notification-row ${n.read ? "read" : ""}`}
              key={n.id}
            >
              <span className="notification-icon">
                <Bell size={20} />
              </span>
              <div>
                <Link to={n.link}>
                  <h3>{n.title}</h3>
                </Link>
                <p>{n.body}</p>
                <small>{date(n.created_at)}</small>
              </div>
              <Button
                disabled={busy || n.read}
                onClick={() =>
                  run(
                    () => post("/notifications/" + n.id + "/read"),
                    "Marked as read.",
                  )
                }
              >
                <Check size={15} />
                {n.read ? "Read" : "Mark read"}
              </Button>
            </article>
          ))
        ) : (
          <Empty
            title="You're all caught up"
            body="New updates will appear here."
          />
        )}
      </section>
    </>
  );
}
