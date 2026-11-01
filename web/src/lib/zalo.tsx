import type { components } from '@tms/api-client'
import { Tag } from 'antd'

import { fmtDateTime } from './labels'

export type ZaloInfo = components['schemas']['ZaloLinkInfo']

export function ZaloStatusTag({ info = { status: 'NOT_INVITED' } }: { info?: ZaloInfo }) {
  if (info.status === 'ACTIVE')
    return (
      <Tag color="green" title={info.activated_at ? `Kích hoạt ${fmtDateTime(info.activated_at)}` : undefined}>
        Đã liên kết{info.display_name ? `: ${info.display_name}` : ''}
      </Tag>
    )
  if (info.status === 'PENDING')
    return <Tag color="gold">Chờ nhập mã (hạn {fmtDateTime(info.code_expires_at!)})</Tag>
  return <Tag>Chưa liên kết</Tag>
}
