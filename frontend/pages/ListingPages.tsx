import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Bath,
  BedDouble,
  Building2,
  House,
  MapPin,
  Plus,
  Ruler,
} from "lucide-react";
import { date, money, post, put, useApi, words } from "../api";
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
import type { Contact, Deal, Page, Property } from "../types";

export function PropertiesPage() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Property | "new" | null>(null);
  const [selected, setSelected] = useState<Property | null>(null);
  const query = useApi<Page<Property>>(
    `/crm/properties?q=${encodeURIComponent(q)}&page=${page}`,
  );
  const { busy, run } = useAction();
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.currentTarget));
    const body = {
      ...d,
      price: Number(d.price),
      bedrooms: Number(d.bedrooms),
      bathrooms: Number(d.bathrooms),
      sqft: d.sqft ? Number(d.sqft) : null,
      features: String(d.features)
        .split(",")
        .map((f) => f.trim())
        .filter(Boolean),
    };
    const result = await run(
      () =>
        editing && editing !== "new"
          ? put(`/crm/properties/${editing.id}`, body)
          : post("/crm/properties", body),
      "Property saved.",
    );
    if (result) {
      setEditing(null);
      setSelected(null);
    }
  };
  const current = editing && editing !== "new" ? editing : null;
  return (
    <>
      <PageTitle
        eyebrow="THE RIGHT PLACE, FOR THE RIGHT PERSON"
        title="Your property collection"
        description="A clear view of the homes in your clients' next chapter."
        action={
          <Button variant="primary" onClick={() => setEditing("new")}>
            <Plus size={17} />
            Add property
          </Button>
        }
      />
      <div className="list-toolbar">
        <SearchBox
          value={q}
          onChange={(v) => {
            setQ(v);
            setPage(1);
          }}
          placeholder="Search property addresses"
        />
        <Badge>{query.data?.total || 0} properties</Badge>
      </div>
      {query.isLoading ? (
        <Loading />
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : query.data?.items.length ? (
        <>
          <div className="property-grid">
            {query.data.items.map((p, index) => (
              <article className="property-card" key={p.id}>
                <button
                  className={`property-identity tone-${index % 4}`}
                  onClick={() => setSelected(p)}
                  aria-label={"View " + p.address}
                >
                  <span className="property-number">
                    {p.address.split(" ")[0]}
                  </span>
                  <div>
                    <House size={25} />
                    <span>{words(p.property_type)}</span>
                  </div>
                  <Badge>{words(p.status)}</Badge>
                </button>
                <div className="property-info">
                  <strong className="property-price">{money(p.price)}</strong>
                  <h2>
                    <button onClick={() => setSelected(p)}>{p.address}</button>
                  </h2>
                  <p>
                    <MapPin size={14} />
                    {p.location}
                  </p>
                  <div className="property-specs">
                    <span>
                      <BedDouble size={17} />
                      {p.bedrooms} beds
                    </span>
                    <span>
                      <Bath size={17} />
                      {p.bathrooms} baths
                    </span>
                    {p.sqft && (
                      <span>
                        <Ruler size={17} />
                        {p.sqft.toLocaleString()} ft²
                      </span>
                    )}
                  </div>
                  <div className="property-card-footer">
                    <small>
                      {p.source === "fictional_demo"
                        ? "Fictional demo property"
                        : p.source}
                    </small>
                    <button
                      className="text-button"
                      onClick={() => setSelected(p)}
                    >
                      View details <ArrowRight size={15} />
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
          <Pager page={page} total={query.data.total} onPage={setPage} />
        </>
      ) : (
        <Empty
          title="Make room for your first listing"
          body="Add a property to compare it with your buyers' confirmed preferences."
        />
      )}
      {editing && (
        <Modal
          title={current ? "Edit property" : "Add a property"}
          onClose={() => setEditing(null)}
          wide
        >
          <form onSubmit={save}>
            <Field label="Street address">
              <input name="address" required defaultValue={current?.address} />
            </Field>
            <div className="form-grid">
              <Field label="City or area">
                <input
                  name="location"
                  required
                  defaultValue={current?.location}
                />
              </Field>
              <Field label="Price ($)">
                <input
                  name="price"
                  type="number"
                  min="0"
                  required
                  defaultValue={current?.price}
                />
              </Field>
              <Field label="Bedrooms">
                <input
                  name="bedrooms"
                  type="number"
                  min="0"
                  required
                  defaultValue={current?.bedrooms}
                />
              </Field>
              <Field label="Bathrooms">
                <input
                  name="bathrooms"
                  type="number"
                  min="0"
                  step="0.5"
                  required
                  defaultValue={current?.bathrooms}
                />
              </Field>
              <Field label="Square feet">
                <input
                  name="sqft"
                  type="number"
                  min="1"
                  defaultValue={current?.sqft || ""}
                />
              </Field>
              <Field label="Property type">
                <select
                  name="property_type"
                  defaultValue={current?.property_type || "single_family"}
                >
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
              <Field label="Listing status">
                <select
                  name="status"
                  defaultValue={current?.status || "active"}
                >
                  {["active", "pending", "sold", "withdrawn"].map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </Field>
              <Field label="Source">
                <input
                  name="source"
                  defaultValue={current?.source || "manual"}
                />
              </Field>
            </div>
            <Field label="Features (comma separated)">
              <input
                name="features"
                defaultValue={current?.features.join(", ")}
              />
            </Field>
            <Submit busy={busy} label="Save property" />
          </form>
        </Modal>
      )}
      {selected && (
        <Modal title={selected.address} onClose={() => setSelected(null)}>
          <Badge tone="green">{words(selected.status)}</Badge>
          <h2>{money(selected.price)}</h2>
          <p>
            <MapPin size={16} />
            {selected.location}
          </p>
          <div className="property-specs">
            <span>{selected.bedrooms} beds</span>
            <span>{selected.bathrooms} baths</span>
            <span>{selected.sqft?.toLocaleString()} ft²</span>
          </div>
          <div className="criteria-features">
            {selected.features.map((f) => (
              <Badge key={f}>{f}</Badge>
            ))}
          </div>
          <p>
            Buyer matches appear in each client's profile and explain every
            matching or conflicting criterion.
          </p>
          <div className="modal-actions">
            <Button
              onClick={() => {
                setEditing(selected);
                setSelected(null);
              }}
            >
              Edit property
            </Button>
            <Link className="button primary" to="/buyers">
              Find a buyer <ArrowRight size={16} />
            </Link>
          </div>
        </Modal>
      )}
    </>
  );
}

const stages = [
  "qualified",
  "showing",
  "offer",
  "under_contract",
  "closed",
  "lost",
];
export function DealsPage() {
  const query = useApi<Page<Deal>>("/crm/deals?page_size=100");
  const contacts = useApi<Page<Contact>>("/crm/contacts?page_size=100");
  const properties = useApi<Page<Property>>("/crm/properties?page_size=100");
  const [editing, setEditing] = useState<Deal | "new" | null>(null);
  const { busy, run } = useAction();
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.currentTarget));
    const body = {
      ...d,
      value: Number(d.value),
      commission_bps: Number(d.commission_bps),
      property_id: d.property_id || null,
      expected_close: d.expected_close
        ? new Date(String(d.expected_close)).toISOString()
        : null,
    };
    const result = await run(
      () =>
        editing && editing !== "new"
          ? put(`/crm/deals/${editing.id}`, body)
          : post("/crm/deals", body),
      "Deal updated.",
    );
    if (result) setEditing(null);
  };
  const current = editing && editing !== "new" ? editing : null;
  return (
    <>
      <PageTitle
        eyebrow="FROM FIRST CONVERSATION TO CLOSING"
        title="Keep things moving."
        description="Your pipeline, with the people and next steps behind every deal."
        action={
          <Button variant="primary" onClick={() => setEditing("new")}>
            <Plus size={17} />
            Add a deal
          </Button>
        }
      />
      {query.isLoading ? (
        <Loading />
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : (
        <>
          <div className="pipeline-summary">
            <Building2 size={23} />
            <div>
              <strong>
                {money(
                  query.data?.items
                    .filter((d) => !["closed", "lost"].includes(d.stage))
                    .reduce((sum, d) => sum + d.value, 0),
                )}
              </strong>
              <span>Active pipeline value</span>
            </div>
            <Badge>{query.data?.total || 0} total deals</Badge>
          </div>
          <div className="kanban">
            {stages
              .filter((s) => s !== "lost")
              .map((stage) => (
                <section className="kanban-column" key={stage}>
                  <div className="kanban-heading">
                    <h2>{words(stage)}</h2>
                    <Badge>
                      {query.data?.items.filter((d) => d.stage === stage)
                        .length || 0}
                    </Badge>
                  </div>
                  {query.data?.items
                    .filter((d) => d.stage === stage)
                    .map((deal) => (
                      <button
                        className="deal-card"
                        key={deal.id}
                        onClick={() => setEditing(deal)}
                      >
                        <span className="deal-icon">
                          <House size={21} />
                        </span>
                        <h3>{deal.title}</h3>
                        <strong>{money(deal.value)}</strong>
                        <p>
                          {contacts.data?.items.find(
                            (c) => c.id === deal.contact_id,
                          )?.name || "Client"}
                        </p>
                        <div>
                          <span>Target close</span>
                          <small>{date(deal.expected_close)}</small>
                        </div>
                      </button>
                    ))}
                  <button
                    className="add-deal"
                    onClick={() => setEditing("new")}
                  >
                    <Plus size={15} />
                    Add deal
                  </button>
                </section>
              ))}
          </div>
          {(query.data?.total || 0) > 100 && (
            <p className="help-text">
              Showing the first 100 deals. The paginated API supports larger
              portfolios.
            </p>
          )}
        </>
      )}
      {editing && (
        <Modal
          title={current ? "Update deal" : "Create a deal"}
          onClose={() => setEditing(null)}
        >
          <form onSubmit={save}>
            <Field label="Deal title">
              <input name="title" required defaultValue={current?.title} />
            </Field>
            <Field label="Client">
              <select
                name="contact_id"
                required
                defaultValue={current?.contact_id}
              >
                <option value="">Choose client</option>
                {contacts.data?.items.map((c) => (
                  <option value={c.id} key={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Property">
              <select
                name="property_id"
                defaultValue={current?.property_id || ""}
              >
                <option value="">Not selected</option>
                {properties.data?.items.map((p) => (
                  <option value={p.id} key={p.id}>
                    {p.address}
                  </option>
                ))}
              </select>
            </Field>
            <div className="form-grid">
              <Field label="Value ($)">
                <input
                  name="value"
                  type="number"
                  min="0"
                  required
                  defaultValue={current?.value || 0}
                />
              </Field>
              <Field label="Stage">
                <select
                  name="stage"
                  defaultValue={current?.stage || "qualified"}
                >
                  {stages.map((s) => (
                    <option value={s} key={s}>
                      {words(s)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Expected closing">
                <input
                  name="expected_close"
                  type="date"
                  defaultValue={current?.expected_close?.slice(0, 10)}
                />
              </Field>
              <Field label="Commission (basis points)" hint="250 = 2.5%">
                <input
                  name="commission_bps"
                  type="number"
                  min="0"
                  max="10000"
                  defaultValue={current?.commission_bps || 250}
                />
              </Field>
            </div>
            <Submit busy={busy} label="Save deal" />
          </form>
          {current && <DealMilestones deal={current} />}
        </Modal>
      )}
    </>
  );
}
function DealMilestones({ deal }: { deal: Deal }) {
  const query = useApi<
    Page<{
      id: string;
      deal_id: string;
      title: string;
      kind: string;
      status: string;
      due_at: string | null;
      amount: number | null;
    }>
  >("/crm/transactions?page_size=100");
  const { busy, run } = useAction();
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const d = Object.fromEntries(new FormData(form));
    const result = await run(
      () =>
        post("/crm/transactions", {
          deal_id: deal.id,
          title: d.title,
          kind: "milestone",
          due_at: d.due_at ? new Date(String(d.due_at)).toISOString() : null,
        }),
      "Milestone added.",
    );
    if (result) form.reset();
  };
  return (
    <section className="milestones">
      <h3>Transaction milestones</h3>
      {query.data?.items
        .filter((m) => m.deal_id === deal.id)
        .map((m) => (
          <div className="milestone" key={m.id}>
            <span>
              {m.title}
              <small>{date(m.due_at)}</small>
            </span>
            <Button
              disabled={busy || m.status === "complete"}
              onClick={() =>
                run(
                  () =>
                    put("/crm/transactions/" + m.id, {
                      deal_id: m.deal_id,
                      title: m.title,
                      kind: m.kind,
                      status: "complete",
                      due_at: m.due_at,
                      amount: m.amount,
                    }),
                  "Milestone completed.",
                )
              }
            >
              {m.status === "complete" ? "Complete" : "Mark complete"}
            </Button>
          </div>
        ))}
      <form onSubmit={submit}>
        <Field label="New milestone">
          <input name="title" required />
        </Field>
        <Field label="Due date">
          <input name="due_at" type="date" />
        </Field>
        <Submit busy={busy} label="Add milestone" />
      </form>
    </section>
  );
}
