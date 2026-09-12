import { useQuery } from "@tanstack/react-query";

export class ApiError extends Error {
  status: number;
  code: string;
  retryAfter: number | null;
  constructor(
    status: number,
    code: string,
    message: string,
    retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const encodedCsrf =
    document.cookie
      .split("; ")
      .find((v) => v.startsWith("realty_csrf="))
      ?.split("=")[1] || "";
  let csrf = "";
  try {
    csrf = decodeURIComponent(encodedCsrf);
  } catch {
    /* A malformed cookie must not crash the client. */
  }
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("X-CSRF-Token", csrf);
  let response: Response;
  try {
    response = await fetch("/api/v1" + path, {
      ...options,
      credentials: "include",
      headers,
    });
  } catch (error) {
    if (
      options.signal?.aborted ||
      (error instanceof Error && error.name === "AbortError")
    )
      throw error;
    throw new ApiError(
      0,
      "network_unavailable",
      options.method && options.method !== "GET"
        ? "The connection was interrupted. Refresh to check whether your change was saved before trying again."
        : "Cannot reach RealtyAI. Check your connection and try again.",
    );
  }
  if (response.status === 204) return undefined as T;
  let data: { error?: { code?: unknown; message?: unknown } } | null;
  try {
    data = await response.json();
  } catch (error) {
    if (options.signal?.aborted) throw error;
    data = null;
  }
  if (!response.ok)
    throw new ApiError(
      response.status,
      typeof data?.error?.code === "string"
        ? data.error.code
        : "request_failed",
      typeof data?.error?.message === "string"
        ? data.error.message
        : "RealtyAI is temporarily unavailable. Refresh to check the current state before trying again.",
      retryAfterSeconds(response.headers.get("Retry-After")),
    );
  if (data === null)
    throw new ApiError(
      response.status,
      "invalid_response",
      "The server response could not be read. Refresh to check the current state.",
    );
  return data as T;
}
export function retryAfterSeconds(value: string | null): number | null {
  if (!value) return null;
  const seconds = /^\d+$/.test(value)
    ? Number(value)
    : (Date.parse(value) - Date.now()) / 1000;
  return Number.isFinite(seconds) ? Math.max(0, Math.ceil(seconds)) : null;
}
export function retryRead(failures: number, error: Error): boolean {
  return (
    failures < 1 &&
    error instanceof ApiError &&
    [0, 502, 503, 504].includes(error.status) &&
    (error.retryAfter === null || error.retryAfter <= 5)
  );
}
export function useApi<T>(path: string, enabled = true) {
  return useQuery({
    queryKey: [path],
    queryFn: ({ signal }) => api<T>(path, { signal }),
    enabled,
    retry: retryRead,
    retryDelay: (_attempt, error) =>
      error instanceof ApiError && error.retryAfter !== null
        ? Math.max(1000, error.retryAfter * 1000)
        : 1000,
    staleTime: 15_000,
  });
}
export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const put = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const money = (value: number | null | undefined) =>
  value == null
    ? "Not recorded"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      }).format(value);
export const parsedDate = (value: string): Date =>
  new Date(
    /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)
      ? value
      : value.includes("T")
        ? value + "Z"
        : value + "T00:00:00Z",
  );
export const date = (
  value: string | null | undefined,
  options: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" },
) =>
  value
    ? Number.isNaN(parsedDate(value).getTime())
      ? "Not set"
      : parsedDate(value).toLocaleDateString("en-US", options)
    : "Not set";
export const time = (value: string, timeZone?: string) =>
  parsedDate(value).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  });
export const words = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
