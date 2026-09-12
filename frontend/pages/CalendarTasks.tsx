import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { CalendarDays, Check, Clock3, Plus, Sparkles } from "lucide-react";
import { date, post, put, time, useApi, words } from "../api";
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
} from "../components";
import type { Appointment, Contact, Page, Task } from "../types";

export function TasksPage() {
  const [filter, setFilter] = useState("open");
  const [editing, setEditing] = useState<Task | "new" | null>(null);
  const query = useApi<Page<Task>>(
    "/crm/tasks?page_size=100" + (filter ? "&status=" + filter : ""),
  );
  const contacts = useApi<Page<Contact>>("/crm/contacts?page_size=100");
  const { busy, run } = useAction();
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.currentTarget));
    const body = {
      ...d,
      contact_id: d.contact_id || null,
      due_at: d.due_at ? new Date(String(d.due_at)).toISOString() : null,
    };
    const result = await run(
      () =>
        editing && editing !== "new"
          ? put(`/crm/tasks/${editing.id}`, body)
          : post("/crm/tasks", body),
      "Task saved.",
    );
    if (result) setEditing(null);
  };
  const complete = (task: Task) =>
    run(
      () =>
        put(`/crm/tasks/${task.id}`, {
          title: task.title,
          contact_id: task.contact_id,
          assigned_to: task.assigned_to,
          priority: task.priority,
          status: task.status === "done" ? "open" : "done",
          due_at: task.due_at,
        }),
      "Task updated.",
    );
  const current = editing && editing !== "new" ? editing : null;
  return (
    <>
      <PageTitle
        eyebrow="SMALL STEPS. REAL PROGRESS."
        title="Your next steps"
        description="Commitments and details that keep your relationships moving."
        action={
          <Button variant="primary" onClick={() => setEditing("new")}>
            <Plus size={17} />
            Add task
          </Button>
        }
      />
      <div className="tabs">
        {[
          ["open", "To do"],
          ["done", "Completed"],
          ["", "All tasks"],
        ].map(([value, label]) => (
          <button
            key={value}
            className={filter === value ? "active" : ""}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <section className="section-card task-list">
        {query.isLoading ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : query.data?.items.length ? (
          query.data.items.map((t) => (
            <article
              className={`task-row ${t.status === "done" ? "done" : ""}`}
              key={t.id}
            >
              <button
                className="task-checkbox"
                disabled={busy}
                aria-label={
                  (t.status === "done" ? "Reopen " : "Complete ") + t.title
                }
                onClick={() => complete(t)}
              >
                {t.status === "done" && <Check size={17} />}
              </button>
              <div>
                <button className="task-title" onClick={() => setEditing(t)}>
                  {t.title}
                </button>
                <small>
                  {contacts.data?.items.find((c) => c.id === t.contact_id)
                    ?.name || "Workspace task"}
                </small>
              </div>
              <Badge
                tone={
                  t.priority === "urgent"
                    ? "red"
                    : t.priority === "high"
                      ? "amber"
                      : "neutral"
                }
              >
                {words(t.priority)}
              </Badge>
              <span
                className={
                  t.due_at &&
                  new Date(t.due_at + "Z") < new Date() &&
                  t.status === "open"
                    ? "overdue"
                    : "task-due"
                }
              >
                <Clock3 size={15} />
                {date(t.due_at)}
              </span>
            </article>
          ))
        ) : (
          <Empty
            title="A clear task list"
            body="Add a task or approve a suggested commitment to start."
          />
        )}
      </section>
      {editing && (
        <Modal
          title={current ? "Edit task" : "Add a task"}
          onClose={() => setEditing(null)}
        >
          <form onSubmit={save}>
            <Field label="Task">
              <input
                name="title"
                required
                maxLength={250}
                defaultValue={current?.title}
              />
            </Field>
            <Field label="Client">
              <select
                name="contact_id"
                defaultValue={current?.contact_id || ""}
              >
                <option value="">Workspace task</option>
                {contacts.data?.items.map((c) => (
                  <option value={c.id} key={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Due date">
              <input
                name="due_at"
                type="datetime-local"
                defaultValue={current?.due_at?.slice(0, 16)}
              />
            </Field>
            <div className="form-grid">
              <Field label="Priority">
                <select
                  name="priority"
                  defaultValue={current?.priority || "normal"}
                >
                  {["normal", "high", "urgent"].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </Field>
              <Field label="Status">
                <select name="status" defaultValue={current?.status || "open"}>
                  {["open", "done", "cancelled"].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
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
export function CalendarPage() {
  const query = useApi<Page<Appointment>>("/crm/appointments?page_size=100");
  const contacts = useApi<Page<Contact>>("/crm/contacts?page_size=100");
  const [editing, setEditing] = useState<Appointment | "new" | null>(null);
  const [showSlots, setShowSlots] = useState(false);
  const slots = useApi<{
    slots: { start_at: string; end_at: string; reason: string }[];
    timezone: string;
    limitations: string;
  }>("/availability", showSlots);
  const [slot, setSlot] = useState<{ start_at: string; end_at: string } | null>(
    null,
  );
  const { busy, run } = useAction();
  const current = editing && editing !== "new" ? editing : null;
  const save = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.currentTarget));
    const external = d.destination === "google";
    const body = {
      title: d.title,
      location: d.location,
      contact_id: d.contact_id || null,
      start_at: new Date(String(d.start_at)).toISOString(),
      end_at: new Date(String(d.end_at)).toISOString(),
    };
    const result = await run(
      () =>
        external
          ? post("/actions", {
              kind: current?.external_id
                ? "calendar_update"
                : "calendar_create",
              title: "Schedule: " + String(d.title),
              reason: "Calendar event prepared for your review.",
              contact_id: d.contact_id || null,
              payload: current?.external_id
                ? { appointment_id: current.id, event: body }
                : body,
            })
          : current
            ? put(`/crm/appointments/${current.id}`, body)
            : post("/crm/appointments", body),
      external
        ? "Calendar suggestion added to AI actions for approval."
        : "Appointment saved.",
    );
    if (result) {
      setEditing(null);
      setSlot(null);
    }
  };
  const sorted = [...(query.data?.items || [])]
    .filter((a) => a.status !== "cancelled")
    .sort((a, b) => a.start_at.localeCompare(b.start_at));
  return (
    <>
      <PageTitle
        eyebrow="BE READY FOR THE MOMENTS THAT MATTER"
        title="Your time, well spent."
        description="Appointments, preparation and a little breathing room."
        action={
          <div className="button-group">
            <Button onClick={() => setShowSlots(true)}>
              <Sparkles size={17} />
              Find a time
            </Button>
            <Button variant="primary" onClick={() => setEditing("new")}>
              <Plus size={17} />
              Add appointment
            </Button>
          </div>
        }
      />
      <section className="section-card calendar-list">
        <div className="section-heading">
          <h2>
            <CalendarDays size={20} />
            Upcoming & recorded appointments
          </h2>
          <Button
            disabled={busy}
            onClick={() =>
              run(
                () => post("/integrations/google/sync?resource=calendar"),
                "Calendar sync queued.",
              )
            }
          >
            Sync Google Calendar
          </Button>
        </div>
        {query.isLoading ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : sorted.length ? (
          sorted.map((a) => (
            <article className="calendar-row" key={a.id}>
              <div className="calendar-day">
                <strong>{date(a.start_at, { day: "numeric" })}</strong>
                <span>{date(a.start_at, { month: "short" })}</span>
              </div>
              <div className="calendar-time">
                <strong>{time(a.start_at)}</strong>
                <span>{time(a.end_at)}</span>
              </div>
              <div className="calendar-description">
                <h3>{a.title}</h3>
                <p>{a.location || "Location not set"}</p>
                <Badge tone={a.external_id ? "blue" : "neutral"}>
                  {a.external_id ? "Google Calendar" : "Local appointment"}
                </Badge>
              </div>
              <div className="button-group">
                {a.contact_id && (
                  <Link
                    className="button secondary"
                    to={"/contacts/" + a.contact_id}
                  >
                    <Sparkles size={16} />
                    Prepare
                  </Link>
                )}
                <Button onClick={() => setEditing(a)}>Edit</Button>
              </div>
            </article>
          ))
        ) : (
          <Empty
            title="Make space for a conversation"
            body="Add an appointment or connect Google Calendar to start."
          />
        )}
      </section>
      {editing && (
        <Modal
          title={current ? "Edit appointment" : "Schedule an appointment"}
          onClose={() => {
            setEditing(null);
            setSlot(null);
          }}
        >
          <form onSubmit={save}>
            <Field label="Appointment title">
              <input name="title" required defaultValue={current?.title} />
            </Field>
            <Field label="Client">
              <select
                name="contact_id"
                defaultValue={current?.contact_id || ""}
              >
                <option value="">No client selected</option>
                {contacts.data?.items.map((c) => (
                  <option value={c.id} key={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
            <div className="form-grid">
              <Field label="Starts">
                <input
                  name="start_at"
                  type="datetime-local"
                  required
                  defaultValue={localInput(current?.start_at || slot?.start_at)}
                />
              </Field>
              <Field label="Ends">
                <input
                  name="end_at"
                  type="datetime-local"
                  required
                  defaultValue={localInput(current?.end_at || slot?.end_at)}
                />
              </Field>
            </div>
            <Field label="Location">
              <input name="location" defaultValue={current?.location} />
            </Field>
            <Field label="Save to">
              <select
                name="destination"
                defaultValue={current?.external_id ? "google" : "local"}
                disabled={!!current?.external_id}
              >
                {!current?.external_id && (
                  <option value="local">Local workspace calendar</option>
                )}
                <option value="google">
                  Google Calendar · Requires approval
                </option>
              </select>
              {current?.external_id && (
                <input name="destination" type="hidden" value="google" />
              )}
            </Field>
            <Submit busy={busy} label="Save appointment" />
          </form>
          {current?.external_id && (
            <Button
              onClick={async () => {
                const result = await run(
                  () =>
                    post("/actions", {
                      kind: "calendar_delete",
                      title: "Cancel: " + current.title,
                      reason: "Calendar cancellation prepared for review.",
                      contact_id: current.contact_id,
                      payload: { appointment_id: current.id },
                    }),
                  "Cancellation added to AI actions for approval.",
                );
                if (result) setEditing(null);
              }}
            >
              Request cancellation
            </Button>
          )}
        </Modal>
      )}
      {showSlots && (
        <Modal title="Available times" onClose={() => setShowSlots(false)}>
          {slots.isLoading ? (
            <Loading />
          ) : slots.error ? (
            <ErrorState error={slots.error} />
          ) : (
            <>
              <p>
                Office hours in {slots.data?.timezone}.{" "}
                {slots.data?.limitations}
              </p>
              <div className="slot-list">
                {slots.data?.slots.map((s) => (
                  <button
                    key={s.start_at}
                    onClick={() => {
                      setSlot(s);
                      setShowSlots(false);
                      setEditing("new");
                    }}
                  >
                    <CalendarDays size={18} />
                    <span>
                      {date(s.start_at)} · {time(s.start_at)}–{time(s.end_at)}
                      <small>{s.reason}</small>
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </Modal>
      )}
    </>
  );
}
function localInput(value: string | undefined) {
  if (!value) return "";
  const d = new Date(value.endsWith("Z") ? value : value + "Z");
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
