const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function csrfToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie.split("; ").find((part) => part.startsWith("mentor_csrf="))?.split("=")[1];
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method.toUpperCase())) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", decodeURIComponent(token));
  }
  const response = await fetch(API_URL + path, { ...init, headers, credentials: "include" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Не удалось выполнить запрос");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type User = {
  id: string;
  email: string;
  email_verified: boolean;
  profile: { display_name: string | null; experience_level: string | null; onboarding_completed: boolean } | null;
  goal: { target_role: string; weekly_minutes: number; motivation: string | null } | null;
};

export type AuthResponse = { user: User; onboarding_required: boolean };
export type OnboardingResponse = { completed: boolean; profile: User["profile"]; goal: User["goal"] };
