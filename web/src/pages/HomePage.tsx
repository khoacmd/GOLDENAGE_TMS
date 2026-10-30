import { Card, Descriptions, Tag } from 'antd'

import { useAuth } from '../auth-context'

const ROLE_LABELS: Record<string, string> = {
  company_admin: 'Admin công ty',
  manager: 'Quản lý',
  warehouse_keeper: 'Thủ kho',
  driver: 'Nhân viên giao hàng',
}

export function HomePage() {
  const { me } = useAuth()
  if (!me) return null
  return (
    <Card title="Thông tin tài khoản">
      <Descriptions column={1}>
        <Descriptions.Item label="Tên đăng nhập">{me.username}</Descriptions.Item>
        <Descriptions.Item label="Họ tên">{me.full_name}</Descriptions.Item>
        <Descriptions.Item label="Công ty">{me.company?.name ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="Vai trò">
          {me.is_system_admin && <Tag color="red">Admin hệ thống</Tag>}
          {me.roles.map((r) => (
            <Tag key={r} color="blue">
              {ROLE_LABELS[r] ?? r}
            </Tag>
          ))}
        </Descriptions.Item>
      </Descriptions>
    </Card>
  )
}
