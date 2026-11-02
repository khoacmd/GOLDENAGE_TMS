import { createApiClient, type TokenPair, type TokenStore } from '@tms/api-client'

// Token chỉ giữ trong bộ nhớ: mỗi lần mở mini app đăng nhập lại ngầm bằng token Zalo.
let current: TokenPair | null = null
let onExpired: (() => void) | null = null

export const tokenStore: TokenStore = {
  get: () => current,
  set(tokens) {
    const expired = current !== null && tokens === null
    current = tokens
    if (expired) onExpired?.()
  },
}

export function setSessionExpiredHandler(handler: () => void) {
  onExpired = handler
}

export const api = createApiClient(import.meta.env.VITE_API_URL ?? '', tokenStore, {
  async refresh(refreshToken, client) {
    const { data } = await client.POST('/api/v1/auth/zalo/refresh', {
      body: { refresh_token: refreshToken },
    })
    if (!data?.access_token || !data.refresh_token) return null
    return {
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      token_type: data.token_type,
    }
  },
})
