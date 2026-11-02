import { errorMessage, type components } from '@tms/api-client'
import { useQueryClient } from '@tanstack/react-query'
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { api, setSessionExpiredHandler, tokenStore } from './api'
import { SessionContext, type Account, type Session, type SessionState } from './useSession'
import { zaloToken } from './zalo'

type LoginOut = components['schemas']['ZaloLoginOut']

const CHOICE_KEY = 'tms-zalo-account'

interface Choice {
  company_id: string
  kind: Account['kind']
}

async function requestLogin(choice: Choice | null) {
  const access_token = await zaloToken()
  return api.POST('/api/v1/auth/zalo/login', {
    body: { access_token, company_id: choice?.company_id, kind: choice?.kind },
  })
}

function savedChoice(): Choice | null {
  try {
    const raw = localStorage.getItem(CHOICE_KEY)
    return raw ? (JSON.parse(raw) as Choice) : null
  } catch {
    return null
  }
}

function saveChoice(choice: Choice | null) {
  try {
    if (choice) localStorage.setItem(CHOICE_KEY, JSON.stringify(choice))
    else localStorage.removeItem(CHOICE_KEY)
  } catch {
    // Không lưu được thì lần sau chọn lại.
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [state, setState] = useState<SessionState>({ status: 'loading' })
  const [initialCode] = useState(() => new URLSearchParams(window.location.search).get('code'))
  const [activating, setActivating] = useState(Boolean(initialCode))

  const apply = useCallback(
    (out: LoginOut) => {
      if (out.status === 'not_linked') {
        setState({ status: 'not_linked', zaloName: out.zalo_name })
      } else if (out.status === 'choose_account') {
        setState({ status: 'choose', accounts: out.accounts })
      } else if (out.account && out.access_token && out.refresh_token) {
        tokenStore.set({
          access_token: out.access_token,
          refresh_token: out.refresh_token,
          token_type: out.token_type,
        })
        queryClient.clear()
        saveChoice({ company_id: out.account.company.id, kind: out.account.kind })
        setActivating(false)
        setState({ status: 'ready', account: out.account })
      }
    },
    [queryClient],
  )

  const login = useCallback(
    async (choice: Choice | null) => {
      try {
        let result = await requestLogin(choice)
        // Tài khoản đã nhớ không còn liên kết → đăng nhập lại không kèm lựa chọn.
        if (!result.data && choice && result.response.status === 401) {
          saveChoice(null)
          result = await requestLogin(null)
        }
        const { data, error } = result
        if (data) return apply(data)
        setState({ status: 'error', message: errorMessage(error, 'Không đăng nhập được') })
      } catch (e) {
        console.warn('Đăng nhập Zalo lỗi', e)
        setState({ status: 'error', message: 'Không kết nối được máy chủ, vui lòng thử lại' })
      }
    },
    [apply],
  )

  const relogin = useCallback(
    (choice: Choice | null) => {
      setState({ status: 'loading' })
      void login(choice)
    },
    [login],
  )

  useEffect(() => {
    setSessionExpiredHandler(() => relogin(savedChoice()))
    // oxlint-disable-next-line react/set-state-in-effect -- login chỉ setState sau khi có kết quả mạng.
    void login(savedChoice())
  }, [login, relogin])

  const session = useMemo<Session>(
    () => ({
      state,
      initialCode,
      activating,
      setActivating,
      retry: () => relogin(savedChoice()),
      choose: (account) => relogin({ company_id: account.company.id, kind: account.kind }),
      switchAccount: () => {
        saveChoice(null)
        relogin(null)
      },
      async activate(code) {
        try {
          const access_token = await zaloToken()
          const { data, error } = await api.POST('/api/v1/auth/zalo/activate', {
            body: { access_token, code },
          })
          if (!data) return errorMessage(error, 'Không kích hoạt được mã')
          apply(data)
          return null
        } catch (e) {
          console.warn('Kích hoạt lỗi', e)
          return 'Không kết nối được máy chủ, vui lòng thử lại'
        }
      },
    }),
    [state, initialCode, activating, relogin, apply],
  )

  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>
}
