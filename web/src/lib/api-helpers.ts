import { errorMessage } from '@tms/api-client'
import { useState } from 'react'

/** Lấy `data` từ kết quả openapi-fetch, ném Error (thông báo tiếng Việt) nếu lỗi. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data !== undefined) return result.data
  const status = result.response.status
  if (status === 422) throw new Error('Dữ liệu nhập chưa hợp lệ')
  if (status === 403) throw new Error('Bạn không có quyền thực hiện thao tác này')
  throw new Error(errorMessage(result.error))
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
