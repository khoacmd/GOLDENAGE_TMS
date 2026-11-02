import type { components } from '@tms/api-client'
import { createContext, useContext } from 'react'

export type Account = components['schemas']['ZaloAccount']

export type SessionState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'not_linked'; zaloName?: string | null }
  | { status: 'choose'; accounts: Account[] }
  | { status: 'ready'; account: Account }

export interface Session {
  state: SessionState
  /** Mã trong link/QR kích hoạt (nếu mở mini app từ đó). */
  initialCode: string | null
  /** Đang nhập thêm mã khi đã đăng nhập (liên kết công ty/liên hệ khác). */
  activating: boolean
  setActivating(value: boolean): void
  retry(): void
  choose(account: Account): void
  switchAccount(): void
  activate(code: string): Promise<string | null>
}

export const SessionContext = createContext<Session | null>(null)

export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) throw new Error('Thiếu SessionProvider')
  return session
}
