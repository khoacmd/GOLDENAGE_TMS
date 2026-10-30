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
