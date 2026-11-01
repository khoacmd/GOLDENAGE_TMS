import { createApiClient, type TokenPair, type TokenStore } from '@tms/api-client'
import * as SecureStore from 'expo-secure-store'

const STORAGE_KEY = 'tms.tokens'
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000'

// TokenStore của api-client là đồng bộ → giữ bản trong bộ nhớ, ghi xuống SecureStore bất đồng bộ.
let cached: TokenPair | null = null

export const tokenStore: TokenStore = {
  get: () => cached,
  set(tokens) {
    cached = tokens
    void (tokens
      ? SecureStore.setItemAsync(STORAGE_KEY, JSON.stringify(tokens))
      : SecureStore.deleteItemAsync(STORAGE_KEY))
  },
}

export async function loadStoredTokens(): Promise<void> {
  const raw = await SecureStore.getItemAsync(STORAGE_KEY)
  cached = raw ? (JSON.parse(raw) as TokenPair) : null
}

export const api = createApiClient(API_URL, tokenStore)

/** Làm mới access token bằng refresh token (dùng cho request gọi fetch trực tiếp). */
export async function refreshSession(): Promise<boolean> {
  const current = tokenStore.get()
  if (!current) return false
  const { data } = await api.POST('/api/v1/auth/refresh', { body: { refresh_token: current.refresh_token } })
  if (data) tokenStore.set(data)
  return Boolean(data)
}

/** Báo server thu hồi token của phiên (không chờ kết quả - đăng xuất cục bộ luôn diễn ra). */
export function revokeSession(tokens: TokenPair) {
  void api
    .POST('/api/v1/auth/logout', {
      body: { refresh_token: tokens.refresh_token },
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    })
    .catch(() => undefined)
}
