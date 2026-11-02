import { getAccessToken, openPhone, openWebview } from 'zmp-sdk'

/** Dev trên trình duyệt (không có Zalo): token giả, backend bật TMS_ZALO_MOCK. */
function mockToken(): string | null {
  if (!import.meta.env.DEV) return null
  return localStorage.getItem('tms-mock-token') ?? 'mock:zalo-dev:Khách thử'
}

export async function zaloToken(): Promise<string> {
  return mockToken() ?? (await getAccessToken())
}

export function callPhone(phone: string) {
  if (import.meta.env.DEV) window.open(`tel:${phone}`)
  else void openPhone({ phoneNumber: phone })
}

/** Zalo của tài xế = số điện thoại (Zalo ID theo ứng dụng không dùng để nhắn được). */
export function openZalo(phone: string) {
  const url = `https://zalo.me/${phone}`
  if (import.meta.env.DEV) window.open(url)
  else void openWebview({ url })
}
