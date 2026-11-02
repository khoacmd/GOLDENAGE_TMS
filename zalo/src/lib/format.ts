import type { components } from '@tms/api-client'

type OrderStatus = components['schemas']['CustomerOrderStatus']
type AttemptStatus = components['schemas']['DeliveryAttemptStatus']
export type Eta = components['schemas']['CustomerEta']

const TZ = 'Asia/Ho_Chi_Minh'

export const ORDER_STATUS: Record<OrderStatus, { label: string; color: string }> = {
  WAITING: { label: 'Chưa lên lịch', color: '#6b7280' },
  SCHEDULED: { label: 'Đã lên lịch', color: '#0369a1' },
  IN_TRANSIT: { label: 'Đang giao', color: '#006af5' },
  PARTIAL: { label: 'Đã giao một phần', color: '#b45309' },
  DELIVERED: { label: 'Đã giao', color: '#15803d' },
  FAILED: { label: 'Giao không thành công', color: '#b91c1c' },
  CANCELLED: { label: 'Đã hủy', color: '#6b7280' },
}

export const ATTEMPT_STATUS: Record<AttemptStatus, string> = {
  SCHEDULED: 'Đã lên lịch',
  IN_TRANSIT: 'Đang giao',
  DELIVERED: 'Đã giao',
  FAILED: 'Không thành công',
}

export const TEMP_GROUP: Record<string, string> = { DRY: 'Hàng khô', COLD: 'Hàng lạnh' }

export function time(value: string): string {
  return new Date(value).toLocaleTimeString('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: TZ,
  })
}

export function dateTime(value: string): string {
  const date = new Date(value).toLocaleDateString('vi-VN', {
    day: '2-digit',
    month: '2-digit',
    timeZone: TZ,
  })
  return `${time(value)} ${date}`
}

export function etaText(eta: Eta): string {
  return `${time(eta.earliest)} – ${time(eta.latest)}`
}

/** "2026-11-02" → "T2, 02/11/2026"; xử lý như ngày thuần, không theo múi giờ. */
export function dayLabel(day: string): string {
  const [y, m, d] = day.split('-').map(Number)
  const weekday = new Date(Date.UTC(y, m - 1, d)).getUTCDay()
  const name = weekday === 0 ? 'CN' : `T${weekday + 1}`
  return `${name}, ${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${y}`
}

export function shiftDay(day: string, days: number): string {
  const [y, m, d] = day.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10)
}

export function money(value: string | number): string {
  return `${Number(value).toLocaleString('vi-VN')} đ`
}

export function quantity(value: string | number): string {
  return Number(value).toLocaleString('vi-VN', { maximumFractionDigits: 3 })
}
