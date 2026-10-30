import { createApiClient, type TokenPair, type TokenStore } from '@tms/api-client'

const STORAGE_KEY = 'tms.tokens'

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
