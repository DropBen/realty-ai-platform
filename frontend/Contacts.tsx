import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Mail, Plus, Users } from "lucide-react";
import { date, post, useApi, words } from "./api";
import {
  Avatar,
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
} from "./components";
import type { Contact, Page } from "./types";

export function ContactForm({
  kind = "lead",
  onDone,
}: {
  kind?: string;
  onDone: () => void;
}) {
  const { busy, run } = useAction();
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.currentTarget));
    const result = await run(
      () =>
        post("/crm/contacts", {
          ...data,
          email: data.email || null,
          phone: data.phone || null,
        }),
      "Contact created.",
    );
    if (result) onDone();
  };
  return (
    <form onSubmit={submit}>
      <Field label="Full name">
        <input name="name" required maxLength={160} autoFocus />
      </Field>
      <div className="form-grid">
        <Field label="Email address">
          <input name="email" type="email" />
        </Field>
        <Field label="Phone">
          <input name="phone" type="tel" maxLength={40} />
        </Field>
        <Field label="Relationship">
          <select name="kind" defaultValue={kind}>
            {["lead", "buyer", "seller", "contact"].map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </Field>
        <Field label="Stage">
          <select name="stage" defaultValue="new">
            {["new", "nurturing", "qualified", "active", "closed"].map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </Field>
      </div>
      <div className="modal-actions">
        <Submit busy={busy} label="Create contact" />
      </div>
    </form>
  );
}
export default function Contacts({ kind }: { kind?: string }) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [create, setCreate] = useState(false);
  const [sort, setSort] = useState("created_at");
  const query = useApi<Page<Contact>>(
    `/crm/contacts?page=${page}&q=${encodeURIComponent(q)}&sort=${sort}${kind ? "&kind=" + kind : ""}`,
  );
  return (
    <>
      <PageTitle
        eyebrow="RELATIONSHIPS FIRST"
        title={kind ? words(kind) + "s" : "Your people"}
        description="The context behind every conversation, all in one place."
        action={
          <Button variant="primary" onClick={() => setCreate(true)}>
            <Plus size={17} /> Add {kind || "contact"}
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
            placeholder="Search contacts by name"
          />
          <div className="toolbar-right">
            <Badge>{query.data?.total || 0} relationships</Badge>
            <label className="sort-label">
              Sort by{" "}
              <select value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="created_at">Newest first</option>
                <option value="name">Name</option>
                <option value="updated_at">Recently updated</option>
              </select>
            </label>
          </div>
        </div>
        {query.isLoading ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : query.data?.items.length ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Contact</th>
                    <th>Relationship</th>
                    <th>Stage</th>
                    <th>Intent</th>
                    <th>Last conversation</th>
                    <th>
                      <span className="sr-only">Open profile</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <Link className="person-cell" to={"/contacts/" + c.id}>
                          <Avatar name={c.name} />
                          <span>
                            <strong>{c.name}</strong>
                            <small>
                              <Mail size={12} />
                              {c.email || "Email not recorded"}
                            </small>
                          </span>
                        </Link>
                      </td>
                      <td>
                        <Badge
                          tone={
                            c.kind === "buyer"
                              ? "green"
                              : c.kind === "seller"
                                ? "blue"
                                : "neutral"
                          }
                        >
                          {words(c.kind)}
                        </Badge>
                      </td>
                      <td>{words(c.stage)}</td>
                      <td>
                        <div className="intent" title={c.score_reason}>
                          <span className="intent-meter">
                            <span style={{ width: c.score + "%" }} />
                          </span>
                          {c.score || "—"}
                        </div>
                      </td>
                      <td>{date(c.last_contact_at)}</td>
                      <td>
                        <Link
                          className="icon-button"
                          aria-label={"Open " + c.name}
                          to={"/contacts/" + c.id}
                        >
                          <ArrowRight size={18} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={page} total={query.data.total} onPage={setPage} />
          </>
        ) : (
          <Empty
            title={
              q
                ? "No matching relationships"
                : "Every relationship starts somewhere"
            }
            body={
              q
                ? "Try a different name."
                : "Add your first contact or connect Google to begin building your CRM."
            }
            action={
              <Button onClick={() => setCreate(true)}>
                <Users size={17} />
                Add a contact
              </Button>
            }
          />
        )}
      </div>
      {create && (
        <Modal
          title={"Add a " + (kind || "contact")}
          onClose={() => setCreate(false)}
        >
          <ContactForm kind={kind} onDone={() => setCreate(false)} />
        </Modal>
      )}
    </>
  );
}
