import { errorFields, errorMessage, type ApiFieldError } from '@tms/api-client'
import { useState } from 'react'

/** Lỗi từ API; `fields` chỉ rõ từng trường sai để form hiện ngay dưới ô nhập. */
export class ApiError extends Error {
  readonly fields: ApiFieldError[]

  constructor(message: string, fields: ApiFieldError[] = []) {
    super(message)
    this.fields = fields
  }
}

/** Lấy `data` từ kết quả openapi-fetch, ném ApiError (thông báo tiếng Việt) nếu lỗi. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data !== undefined) return result.data
  // 204 No Content: openapi-fetch trả data = undefined dù request thành công.
  if (result.response.ok) return undefined as T
  if (result.response.status === 403) throw new ApiError('Bạn không có quyền thực hiện thao tác này')
  throw new ApiError(errorMessage(result.error), errorFields(result.error))
}

/** Rule form cho mã (khớp `CodeStr` của backend). */
export const CODE_RULE = {
  pattern: /^[A-Za-z0-9._/-]+$/,
  message: 'Chỉ gồm chữ không dấu, số và các ký tự . _ / - (không có dấu cách)',
}

/** Ô bỏ trống (chuỗi rỗng) gửi lên là null, không phải giá trị sai định dạng. */
export function blankToNull<T>(value: T): T {
  if (value === '') return null as T
  if (Array.isArray(value)) return value.map(blankToNull) as T
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, blankToNull(v)])) as T
  }
  return value
}

export interface Paging {
  q?: string
  limit: number
  offset: number
}

/** Trạng thái tìm kiếm + phân trang cho bảng antd. */
export function usePaging(pageSize = 20) {
  const [q, setQ] = useState<string>()
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(pageSize)
  const params: Paging = { q: q || undefined, limit: size, offset: (page - 1) * size }
  return {
    params,
    search: (value: string) => {
      setQ(value.trim() || undefined)
      setPage(1)
    },
    /** Về trang 1 khi đổi bộ lọc khác ngoài ô tìm kiếm. */
    reset: () => setPage(1),
    pagination: (total: number | undefined) => ({
      current: page,
      pageSize: size,
      total,
      showSizeChanger: true,
      showTotal: (t: number) => `${t} bản ghi`,
      onChange: (p: number, s: number) => {
        setPage(p)
        setSize(s)
      },
    }),
  }
}
