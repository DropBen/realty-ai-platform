import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  Loader2,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import type { Action } from "./types";
import { date, post, words } from "./api";

export function Button({
  children,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string }) {
  const { variant = "secondary", ...rest } = props;
  return (
    <button className={`button ${variant} ${className}`} {...rest}>
      {children}
    </button>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Avatar({
  name,
  size = "normal",
}: {
  name: string;
  size?: string;
}) {
  return (
    <span className={`avatar ${size}`} aria-hidden="true">
      {name
        .split(" ")
        .filter((x) => x !== "&")
        .slice(0, 2)
        .map((x) => x[0])
        .join("")}
    </span>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status" aria-label="Loading">
      <div className="skeleton" />
      <div className="skeleton" />
      <div className="skeleton" />
    </div>
  );
}
export function Empty({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <Sparkles size={28} />
      <h3>{title}</h3>
      <p>{body}</p>
      {action}
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle />
      <div>
        <strong>We couldn't load this</strong>
        <p>{error.message}</p>
        {retry && <Button onClick={retry}>Try again</Button>}
      </div>
    </div>
  );
}
export function PageTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}
export function SearchBox({
  value,
  onChange,
  placeholder = "Search",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="search-box">
      <Search size={18} />
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? "wide" : ""}`}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      aria-label={title}
    >
      <div className="modal-inner">
        <div className="modal-heading">
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
const ToastContext = createContext<(text: string, error?: boolean) => void>(
  () => {},
);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(
    null,
  );
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  return (
    <ToastContext.Provider
      value={(text, error = false) => setToast({ text, error })}
    >
      {children}
      {toast && (
        <div
          className={`toast ${toast.error ? "error" : ""}`}
          role={toast.error ? "alert" : "status"}
        >
          {toast.error ? <AlertCircle size={19} /> : <CheckCircle2 size={19} />}
          <span>{toast.text}</span>
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setToast(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}
    </ToastContext.Provider>
  );
}
export const useToast = () => useContext(ToastContext);
export function useAction() {
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const client = useQueryClient();
  async function run<T>(
    fn: () => Promise<T>,
    message = "Saved successfully",
  ): Promise<T | undefined> {
    setBusy(true);
    try {
      const result = await fn();
      await client.invalidateQueries();
      toast(message);
      return result;
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Something went wrong.",
        true,
      );
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  return { busy, run };
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function Submit({
  busy,
  label = "Save",
}: {
  busy: boolean;
  label?: string;
}) {
  return (
    <Button type="submit" variant="primary" disabled={busy}>
      {busy ? <Loader2 className="spin" size={17} /> : <Check size={17} />}{" "}
      {label}
    </Button>
  );
}
export function Pager({
  page,
  total,
  size = 25,
  onPage,
}: {
  page: number;
  total: number;
  size?: number;
  onPage: (p: number) => void;
}) {
  return (
    <div className="pager">
      <span>
        {total} records · Page {page} of {Math.max(1, Math.ceil(total / size))}
      </span>
      <div>
        <Button disabled={page === 1} onClick={() => onPage(page - 1)}>
          Previous
        </Button>
        <Button
          disabled={page * size >= total}
          onClick={() => onPage(page + 1)}
        >
          Next <ArrowRight size={16} />
        </Button>
      </div>
    </div>
  );
}

export function ActionCard({
  action,
  compact = false,
  canApprove = true,
}: {
  action: Action;
  compact?: boolean;
  canApprove?: boolean;
}) {
  const [review, setReview] = useState(false);
  const [edit, setEdit] = useState(false);
  const [payload, setPayload] = useState(
    JSON.stringify(action.payload, null, 2),
  );
  const [scheduled, setScheduled] = useState("");
  const { busy, run } = useAction();
  const pending = ["pending", "snoozed"].includes(action.status);
  const decide = async (decision: string, extra: object = {}) => {
    const result = await run(
      () =>
        post(`/actions/${action.id}/decision`, {
          decision,
          version: action.version,
          ...extra,
        }),
      decision === "approve"
        ? "Approved and queued for execution."
        : `Suggestion ${decision === "reject" ? "rejected" : decision === "undo" ? "undone" : "updated"}.`,
    );
    if (result) {
      setReview(false);
      setEdit(false);
    }
  };
  const submitEdit = async (e: FormEvent) => {
    e.preventDefault();
    await run(async () => {
      const parsed: unknown = JSON.parse(payload);
      return post(`/actions/${action.id}/decision`, {
        decision: "edit",
        version: action.version,
        payload: parsed,
      });
    }, "Draft updated. Review it before approving.");
    setEdit(false);
  };
  return (
    <article className={`action-card ${compact ? "compact" : ""}`}>
      <div className="action-mark">
        <Sparkles size={19} />
      </div>
      <div className="action-content">
        <div className="action-meta">
          <Badge tone={action.priority === "high" ? "amber" : "green"}>
            {words(action.kind)}
          </Badge>
          {action.confidence > 0 && (
            <span>{Math.round(action.confidence * 100)}% confidence</span>
          )}
          <span>{date(action.created_at)}</span>
        </div>
        <h3>{action.title}</h3>
        <p>{action.reason}</p>
        {!pending && (
          <Badge tone={action.status === "succeeded" ? "green" : "neutral"}>
            {words(action.status)}
          </Badge>
        )}
        {action.error_code && (
          <p className="error-text">
            {words(action.error_code)}. Review Settings and the provider before
            retrying.
          </p>
        )}
        <div className="action-controls">
          <Button onClick={() => setReview(true)}>
            {pending ? "Review suggestion" : "View details"}{" "}
            <ArrowRight size={16} />
          </Button>
          {pending && canApprove && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() =>
                decide("snooze", {
                  scheduled_at: new Date(Date.now() + 86400000).toISOString(),
                })
              }
            >
              Tomorrow
            </button>
          )}
          {action.status === "succeeded" &&
            ![
              "send_email",
              "calendar_create",
              "calendar_update",
              "calendar_delete",
            ].includes(action.kind) &&
            canApprove && (
              <button className="text-button" onClick={() => decide("undo")}>
                Undo
              </button>
            )}
        </div>
      </div>
      {review && (
        <Modal
          title="Review assistant suggestion"
          onClose={() => setReview(false)}
        >
          <Badge tone="green">{words(action.permission)}</Badge>
          <h3>{action.title}</h3>
          <p>{action.reason}</p>
          <div className="proposed-change">
            {action.kind === "send_email" ? (
              <>
                <strong>To: {String(action.payload.to)}</strong>
                <h4>{String(action.payload.subject)}</h4>
                <p className="pre-wrap">{String(action.payload.body)}</p>
              </>
            ) : (
              <pre>{JSON.stringify(action.payload, null, 2)}</pre>
            )}
          </div>
          <div className="source-line">
            Source: {action.source_id || "Manual proposal"} ·{" "}
            {action.confidence
              ? `${Math.round(action.confidence * 100)}% confidence`
              : "Confidence not assessed"}
          </div>
          {pending && canApprove && (
            <>
              <Field label="Execute at (optional)">
                <input
                  type="datetime-local"
                  value={scheduled}
                  onChange={(e) => setScheduled(e.target.value)}
                />
              </Field>
              <p className="help-text">
                {action.permission === "approval_required"
                  ? "Approving authorizes the exact external action shown above. Email cannot be unsent."
                  : "The worker will apply this change and record it in the client timeline."}
              </p>
              <div className="modal-actions">
                <Button
                  onClick={() => {
                    setEdit(true);
                    setPayload(JSON.stringify(action.payload, null, 2));
                  }}
                >
                  Edit
                </Button>
                <Button disabled={busy} onClick={() => decide("reject")}>
                  Reject
                </Button>
                <Button
                  variant="primary"
                  disabled={busy}
                  onClick={() =>
                    decide(
                      "approve",
                      scheduled
                        ? { scheduled_at: new Date(scheduled).toISOString() }
                        : {},
                    )
                  }
                >
                  Approve action <Check size={16} />
                </Button>
              </div>
            </>
          )}
          {action.status === "failed" && canApprove && (
            <Button onClick={() => decide("retry")}>
              Return for a new review
            </Button>
          )}
        </Modal>
      )}
      {edit && (
        <Modal title="Edit proposed action" onClose={() => setEdit(false)}>
          <form onSubmit={submitEdit}>
            <Field
              label="Proposed fields"
              hint="Only supported fields are accepted. Saving does not execute the action."
            >
              <textarea
                className="code-input"
                rows={12}
                value={payload}
                onChange={(e) => setPayload(e.target.value)}
              />
            </Field>
            <Submit busy={busy} label="Save draft" />
          </form>
        </Modal>
      )}
    </article>
  );
}
