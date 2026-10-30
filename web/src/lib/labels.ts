import type { components } from '@tms/api-client'

type S = components['schemas']

export const VEHICLE_TYPE: Record<S['VehicleType'], string> = { CAR: 'Ô tô', MOTORBIKE: 'Xe máy' }

export const VEHICLE_REQUIREMENT: Record<S['VehicleRequirement'], string> = {
  CAR: 'Ô tô',
  MOTORBIKE: 'Xe máy',
  ANY: 'Bất kỳ',
}

export const CARGO_CLASS: Record<S['CargoClass'], string> = {
  DRY_ONLY: 'Chỉ hàng khô',
  COLD_ONLY: 'Chỉ hàng đông lạnh',
  ANY: 'Không phân biệt',
}

export const COST_METHOD: Record<S['CostAllocationMethod'], string> = {
  ORDER_VALUE: 'Giá trị đơn',
  DISTANCE: 'Khoảng cách',
  WEIGHT: 'Khối lượng',
  PER_TRIP: 'Chuyến',
}

export const TEMP_CLASS: Record<S['TempClass'], string> = {
  DRY: 'Khô',
  CHILLED: 'Lạnh',
  FROZEN: 'Đông',
}

export const TEMP_GROUP: Record<S['TempGroup'], string> = { DRY: 'Khô', COLD: 'Lạnh/Đông' }

export const ORDER_STATUS: Record<S['OrderStatus'], string> = {
  OPEN: 'Đang xử lý',
  COMPLETED: 'Hoàn thành',
  CANCELLED: 'Đã hủy',
}

export const PART_STATUS: Record<S['OrderPartStatus'], { label: string; color: string }> = {
  PENDING: { label: 'Chờ lập kế hoạch', color: 'default' },
  PLANNED: { label: 'Đã lên kế hoạch', color: 'blue' },
  DELIVERED: { label: 'Đã giao', color: 'green' },
  FAILED: { label: 'Giao thất bại', color: 'red' },
  CANCELLED: { label: 'Đã hủy', color: 'default' },
}

export const ROLE: Record<S['CompanyRole'], string> = {
  company_admin: 'Admin công ty',
  manager: 'Quản lý',
  warehouse_keeper: 'Thủ kho',
  driver: 'Nhân viên giao hàng',
}

export const DEVICE_TYPE: Record<S['DeviceType'], string> = {
  MOBILE: 'Điện thoại',
  PC: 'Máy tính',
  PRINTER: 'Máy in',
}

export const DEVICE_STATUS: Record<S['DeviceStatus'], { label: string; color: string }> = {
  ACTIVE: { label: 'Đang dùng', color: 'green' },
  PENDING: { label: 'Chờ duyệt', color: 'orange' },
  BLOCKED: { label: 'Đã khóa', color: 'red' },
}

export const PRINTER_CONNECTION: Record<S['PrinterConnection'], string> = {
  NETWORK: 'Mạng (LAN/Wi-Fi)',
  USB: 'USB',
  BLUETOOTH: 'Bluetooth',
}

export const PAPER_SIZE: Record<S['PaperSize'], string> = {
  A4: 'A4',
  A5: 'A5',
  K80: 'Giấy nhiệt 80 mm',
}

export const IMPORT_STATUS: Record<S['ImportStatus'], { label: string; color: string }> = {
  VALIDATED: { label: 'Đã kiểm tra', color: 'blue' },
  SUCCEEDED: { label: 'Thành công', color: 'green' },
  FAILED: { label: 'Lỗi', color: 'red' },
}

export const WEEKDAYS = [
  { value: 1, label: 'T2' },
  { value: 2, label: 'T3' },
  { value: 3, label: 'T4' },
  { value: 4, label: 'T5' },
  { value: 5, label: 'T6' },
  { value: 6, label: 'T7' },
  { value: 7, label: 'CN' },
]

export const weekdayText = (days: number[]) =>
  days.map((d) => WEEKDAYS.find((w) => w.value === d)?.label).join(', ')

export function options<K extends string>(labels: Record<K, string>) {
  return (Object.keys(labels) as K[]).map((value) => ({ value, label: labels[value] }))
}

const numberFormat = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 3 })
export const fmtNumber = (v: number | string | null | undefined) =>
  v === null || v === undefined || v === '' ? '' : numberFormat.format(Number(v))

export const fmtDate = (v: string | null | undefined) =>
  v ? new Date(v.length === 10 ? `${v}T00:00:00` : v).toLocaleDateString('vi-VN') : ''

export const fmtDateTime = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleString('vi-VN') : ''

export const TRIP_STATUS: Record<S['TripOrderStatus'], { label: string; color: string }> = {
  DRAFT: { label: 'Nháp', color: 'default' },
  APPROVED: { label: 'Đã duyệt', color: 'blue' },
  PICKED: { label: 'Đã xuất kho', color: 'cyan' },
  DISPATCHED: { label: 'Đang giao', color: 'orange' },
  CLOSED: { label: 'Đã kết thúc', color: 'green' },
  CANCELLED: { label: 'Đã hủy', color: 'red' },
}

export const DELIVERY_STATUS: Record<S['TripDeliveryStatus'], { label: string; color: string }> = {
  NOT_STARTED: { label: 'Chưa giao', color: 'default' },
  IN_PROGRESS: { label: 'Đang giao', color: 'orange' },
  FINISHED: { label: 'Kết thúc', color: 'green' },
}

export const ITEM_STATUS: Record<S['ItemStatus'], { label: string; color: string }> = {
  PENDING: { label: 'Chưa giao', color: 'default' },
  SUCCESS: { label: 'Giao thành công', color: 'green' },
  FAILED: { label: 'Không thành công', color: 'red' },
  CANCELLED: { label: 'Đã hủy', color: 'default' },
}

export const TRIP_ACTION: Record<string, string> = {
  created: 'Lập lệnh',
  updated: 'Sửa lệnh',
  updated_reopened: 'Sửa lệnh đã duyệt (chờ duyệt lại)',
  approved: 'Duyệt lệnh',
  cancelled: 'Hủy lệnh',
  picked: 'Xác nhận xuất kho',
  dispatched: 'Xuất phát',
  item_updated: 'Cập nhật giao hàng',
  closed: 'Kết thúc chuyến',
}
