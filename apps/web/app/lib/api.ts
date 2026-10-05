const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STATUS_MESSAGES: Record<number, string> = {
  401: "Войдите в аккаунт, чтобы продолжить.",
  403: "Не удалось подтвердить запрос. Обновите страницу и попробуйте снова.",
  404: "Материал не найден. Вернитесь к учебному пути.",
  409: "Данные изменились. Обновите материал и повторите действие.",
  422: "Проверьте заполненные поля и попробуйте снова.",
  429: "Слишком много запросов. Подождите минуту и попробуйте снова.",
};
const KNOWN_MESSAGES: Record<string, string> = {
  "Invalid email or password": "Неверный email или пароль.",
  "Unable to create account": "Не удалось создать аккаунт. Попробуйте другой email или войдите.",
  "Complete onboarding first": "Сначала завершите настройку обучения.",
  "Complete prerequisite lessons first": "Сначала пройдите необходимые основы в учебном пути.",
  "Get the knowledge-check questions before submitting": "Загрузите вопросы заново, затем повторите проверку.",
  "Hint level was already revealed": "Эта подсказка уже открыта. Обновите список подсказок.",
  "All hints have already been revealed": "Все подсказки уже открыты.",
  "Reveal the next hint level first": "Открывайте подсказки по порядку.",
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly fieldErrors: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function errorMessage(error: unknown, fallback = "Не удалось выполнить запрос. Попробуйте снова."): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

function csrfToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("mentor_csrf="))?.split("=")[1];
}

function validationMessage(type: unknown): string {
  if (type === "missing") return "Заполните поле.";
  if (type === "string_too_short") return "Значение слишком короткое.";
  if (type === "string_too_long") return "Значение слишком длинное.";
  if (type === "greater_than_equal" || type === "less_than_equal") return "Значение вне допустимого диапазона.";
  return "Проверьте значение поля.";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method.toUpperCase())) {
    const token = csrfToken();
    if (token) headers.set("X-CSRF-Token", decodeURIComponent(token));
  }
  let response: Response;
  try {
    response = await fetch(API_URL + path, { ...init, headers, credentials: "include" });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError("Нет связи с сервером. Проверьте подключение и попробуйте снова.", 0, "network_error");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: unknown; code?: unknown };
    const fieldErrors: Record<string, string> = {};
    if (Array.isArray(body.detail)) {
      for (const item of body.detail) {
        if (item && Array.isArray(item.loc)) {
          const field = item.loc.filter((value: unknown) => typeof value === "string" && value !== "body").join(".");
          if (field) fieldErrors[field] = validationMessage(item.type);
        }
      }
    }
    const message = typeof body.detail === "string" && KNOWN_MESSAGES[body.detail]
      ? KNOWN_MESSAGES[body.detail]
      : STATUS_MESSAGES[response.status] ?? "Сервис временно недоступен. Попробуйте позже.";
    throw new ApiError(message, response.status, typeof body.code === "string" ? body.code : `http_${response.status}`, fieldErrors);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function newRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  if (typeof crypto !== "undefined") crypto.getRandomValues(bytes);
  else for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const value = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${value.slice(0, 8)}-${value.slice(8, 12)}-${value.slice(12, 16)}-${value.slice(16, 20)}-${value.slice(20)}`;
}

export function clearLocalDrafts(): void {
  try {
    for (const key of Object.keys(window.localStorage)) {
      if (key.startsWith("mentor.lesson.draft") || key.startsWith("mentor.generated.draft")) window.localStorage.removeItem(key);
    }
  } catch { /* Browser storage may be unavailable. */ }
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
