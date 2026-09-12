import { useQuery } from "@tanstack/react-query";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const csrf =
    document.cookie
      .split("; ")
      .find((v) => v.startsWith("realty_csrf="))
      ?.split("=")[1] || "";
  const response = await fetch("/api/v1" + path, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      "X-CSRF-Token": decodeURIComponent(csrf),
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok)
    throw new ApiError(
      response.status,
      data.error?.code || "request_failed",
      data.error?.message || "The request failed. Try again.",
    );
  return data as T;
}
export function useApi<T>(path: string, enabled = true) {
  return useQuery({
    queryKey: [path],
    queryFn: () => api<T>(path),
    enabled,
    retry: false,
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
export const date = (
  value: string | null | undefined,
  options: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" },
) =>
  value
    ? new Date(
        value.endsWith("Z") || value.includes("+") ? value : value + "Z",
      ).toLocaleDateString("en-US", options)
    : "Not set";
export const time = (value: string, timeZone?: string) =>
  new Date(value.endsWith("Z") ? value : value + "Z").toLocaleTimeString(
    "en-US",
    { hour: "numeric", minute: "2-digit", timeZone },
  );
export const words = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
