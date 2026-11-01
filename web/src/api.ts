import { createApiClient, type TokenPair, type TokenStore } from '@tms/api-client'

export const STORAGE_KEY = 'tms.tokens'

export const tokenStore: TokenStore = {
  get() {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as TokenPair) : null
  },
  set(tokens) {
    if (tokens) localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens))
    else localStorage.removeItem(STORAGE_KEY)
  },
}

export const api = createApiClient(window.location.origin, tokenStore)

/** Báo server thu hồi token của phiên (không chờ kết quả - đăng xuất cục bộ luôn diễn ra). */
export function revokeSession(tokens: TokenPair) {
  void api
    .POST('/api/v1/auth/logout', {
      body: { refresh_token: tokens.refresh_token },
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    })
    .catch(() => undefined)
}
