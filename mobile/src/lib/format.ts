const number = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 })
export const fmtNumber = (v: number | string | null | undefined) => (v == null ? '' : number.format(Number(v)))
export const fmtDate = (v: string) => {
  const [y, m, d] = v.slice(0, 10).split('-')
  return `${d}/${m}/${y}`
}
export const todayISO = () => {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}
export const shiftDate = (iso: string, days: number) => {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export const TRIP_STATUS: Record<string, { label: string; color: string }> = {
  APPROVED: { label: 'Chờ xuất kho', color: '#8c8c8c' },
  PICKED: { label: 'Sẵn sàng xuất phát', color: '#1677ff' },
  DISPATCHED: { label: 'Đang giao', color: '#fa8c16' },
  CLOSED: { label: 'Đã kết thúc', color: '#389e0d' },
}
export const ITEM_STATUS: Record<string, { label: string; color: string }> = {
  PENDING: { label: 'Chưa giao', color: '#8c8c8c' },
  SUCCESS: { label: 'Thành công', color: '#389e0d' },
  FAILED: { label: 'Không thành công', color: '#cf1322' },
  CANCELLED: { label: 'Đã hủy', color: '#bfbfbf' },
}
export const TEMP_GROUP: Record<string, string> = { DRY: 'Khô', COLD: 'Lạnh/Đông' }
