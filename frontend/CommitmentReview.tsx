import { useState, type FormEvent } from "react";
import { useSession } from "./App";
import { date, post, useApi, words } from "./api";
import { Badge, Button, Field, Modal, Submit, useAction } from "./components";
import type { Commitment } from "./types";

export default function CommitmentReview({ items }: { items: Commitment[] }) {
  const [selected, setSelected] = useState<Commitment | null>(null);
  const session = useSession();
  const members = useApi<{ items: { user_id: string; name: string }[] }>(
    "/account/members",
    !!selected,
  );
  const { busy, run } = useAction();
  const canReview = ["owner", "admin", "agent"].includes(session.role);
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const result = await run(
      () =>
        post(`/commitments/${selected.id}/review`, {
          ...values,
          version: selected.version,
          responsible_user: values.responsible_user || null,
          due_at: values.due_at
            ? new Date(String(values.due_at)).toISOString()
            : null,
        }),
      "Commitment reviewed.",
    );
    if (result) setSelected(null);
  };
  return (
    <section>
      <h3>Commitments to review</h3>
      {!items.length && <p>No commitments have been extracted.</p>}
      {items.map((item) => (
        <article className="commitment-row" key={item.id}>
          <div>
            <strong>{item.title}</strong> <Badge>{words(item.status)}</Badge>
            <p>
              Due: {date(item.due_at)} · Source confidence:{" "}
              {Math.round(item.confidence * 100)}%
            </p>
          </div>
          <Button onClick={() => setSelected(item)}>
            {canReview ? "Review commitment" : "View source"}
          </Button>
        </article>
      ))}
      {selected && (
        <Modal title="Review commitment" onClose={() => setSelected(null)}>
          <p>
            Extracted from a recorded communication. Confirm responsibility and
            timing before setting a reminder.
          </p>
          <blockquote>{selected.quote || selected.title}</blockquote>
          <p className="help-text">Source: {selected.source_id}</p>
          {canReview && (
            <form onSubmit={save}>
              <Field label="Commitment">
                <input
                  name="title"
                  required
                  maxLength={250}
                  defaultValue={selected.title}
                />
              </Field>
              <Field label="Status">
                <select
                  name="status"
                  defaultValue={
                    selected.status === "proposed"
                      ? "confirmed"
                      : selected.status
                  }
                >
                  <option value="confirmed">Confirmed · remind me</option>
                  {selected.status === "confirmed" && (
                    <option value="done">Completed</option>
                  )}
                  <option value="rejected">Rejected</option>
                </select>
              </Field>
              <Field label="Responsible team member">
                <select
                  name="responsible_user"
                  defaultValue={selected.responsible_user || ""}
                >
                  <option value="">Choose a member</option>
                  {members.data?.items.map((member) => (
                    <option key={member.user_id} value={member.user_id}>
                      {member.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field
                label="Due date"
                hint="Uses your browser's local timezone."
              >
                <input
                  name="due_at"
                  type="datetime-local"
                  defaultValue={
                    selected.due_at ? localDate(selected.due_at) : ""
                  }
                />
              </Field>
              <Submit busy={busy} label="Save commitment" />
            </form>
          )}
        </Modal>
      )}
    </section>
  );
}
function localDate(value: string) {
  const date = new Date(value.endsWith("Z") ? value : value + "Z");
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
