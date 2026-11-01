import { errorMessage } from '@tms/api-client'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, type ReactNode } from 'react'

import { STORAGE_KEY, api, revokeSession, tokenStore } from './api'
import { AuthContext, LoginError, type AuthContextValue } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      if (!tokenStore.get()) return null
      const { data, response } = await api.GET('/api/v1/auth/me')
      if (response.status === 401) {
        tokenStore.set(null)
        return null
      }
      return data ?? null
    },
    staleTime: Infinity,
  })

  const login = useCallback(
    async (username: string, password: string, companyCode?: string) => {
      const { data, error } = await api.POST('/api/v1/auth/login', {
        body: { username, password, company_code: companyCode || null },
      })
      if (!data) {
        const body = error as { error?: { code?: string } } | undefined
        throw new LoginError(errorMessage(error, 'Đăng nhập thất bại'), body?.error?.code)
      }
      tokenStore.set(data)
      await queryClient.invalidateQueries({ queryKey: ['me'] })
    },
    [queryClient],
  )

  // Xóa phiên phía trình duyệt. Không dùng `queryClient.clear()`: observer của ['me'] vẫn giữ
  // dữ liệu cũ nên giao diện tiếp tục như đã đăng nhập → đặt `me = null` để về trang đăng nhập.
  const endLocalSession = useCallback(() => {
    void queryClient.cancelQueries()
    queryClient.setQueryData(['me'], null)
    queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
  }, [queryClient])

  const logout = useCallback(() => {
    const tokens = tokenStore.get()
    tokenStore.set(null)
    if (tokens) revokeSession(tokens)
    endLocalSession()
  }, [endLocalSession])

  // Đăng xuất ở tab khác (xóa token trong localStorage) → tab này cũng kết thúc phiên.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue === null) endLocalSession()
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [endLocalSession])

  const value = useMemo<AuthContextValue>(() => {
    const me = meQuery.data ?? null
    return {
      me,
      loading: meQuery.isLoading,
      login,
      logout,
      hasRole: (...roles) => Boolean(me?.roles.some((r) => roles.includes(r))),
    }
  }, [meQuery.data, meQuery.isLoading, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
