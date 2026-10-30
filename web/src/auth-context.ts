import type { CompanyRole, Me } from '@tms/api-client'
import { createContext, useContext } from 'react'

export class LoginError extends Error {
  readonly code?: string

  constructor(message: string, code?: string) {
    super(message)
    this.code = code
  }
}

export interface AuthContextValue {
  me: Me | null
  loading: boolean
  login(username: string, password: string, companyCode?: string): Promise<void>
  logout(): void
  hasRole(...roles: CompanyRole[]): boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth phải nằm trong AuthProvider')
  return ctx
}
