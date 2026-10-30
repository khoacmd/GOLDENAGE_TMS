// Client API dùng chung cho web & mobile, type sinh từ OpenAPI của backend
// (`pnpm api:generate` sau mỗi lần đổi API).
import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };
export type TokenPair = components["schemas"]["TokenPair"];
export type Me = components["schemas"]["MeResponse"];
export type CompanyRole = components["schemas"]["CompanyRole"];

export interface ApiErrorBody {
  error?: { code: string; message: string };
  detail?: unknown;
}

export interface TokenStore {
  get(): TokenPair | null;
  set(tokens: TokenPair | null): void;
}

export function createApiClient(baseUrl: string, tokens: TokenStore) {
  const client = createClient<paths>({ baseUrl });
  // Client riêng cho refresh để không lặp vô hạn qua middleware.
  const refreshClient = createClient<paths>({ baseUrl });
  let refreshing: Promise<boolean> | null = null;

  async function refreshTokens(): Promise<boolean> {
    const current = tokens.get();
    if (!current) return false;
    const { data } = await refreshClient.POST("/api/v1/auth/refresh", {
      body: { refresh_token: current.refresh_token },
    });
    tokens.set(data ?? null);
    return Boolean(data);
  }

  // Middleware trả `undefined` khi không thay request/response: trên React Native,
  // openapi-fetch kiểm tra `instanceof Response` và từ chối object gốc của fetch polyfill.
  const auth: Middleware = {
    onRequest({ request }) {
      const current = tokens.get();
      if (current) request.headers.set("Authorization", `Bearer ${current.access_token}`);
    },
    async onResponse({ request, response }) {
      if (response.status !== 401 || !tokens.get() || request.url.includes("/auth/")) {
        return undefined;
      }
      refreshing ??= refreshTokens().finally(() => {
        refreshing = null;
      });
      if (!(await refreshing)) return undefined;
      const retry = new Request(request);
      retry.headers.set("Authorization", `Bearer ${tokens.get()!.access_token}`);
      return fetch(retry);
    },
  };
  client.use(auth);
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;

export function errorMessage(error: unknown, fallback = "Đã có lỗi xảy ra"): string {
  const body = error as ApiErrorBody | undefined;
  return body?.error?.message ?? fallback;
}
