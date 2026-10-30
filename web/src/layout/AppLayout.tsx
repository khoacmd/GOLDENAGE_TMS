import {
  ApartmentOutlined,
  CarOutlined,
  DatabaseOutlined,
  HomeOutlined,
  InboxOutlined,
  LogoutOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import type { CompanyRole } from '@tms/api-client'
import { Button, Layout, Menu, Space, Spin, Typography } from 'antd'
import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router'

import { useAuth } from '../auth-context'

interface NavItem {
  path: string
  label: string
  icon: ReactNode
  /** Vai trò trong công ty được thấy menu; `system` = admin hệ thống. */
  access: (CompanyRole | 'system' | 'all')[]
}

const NAV_ITEMS: NavItem[] = [
  { path: '/', label: 'Tổng quan', icon: <HomeOutlined />, access: ['all'] },
  { path: '/plans', label: 'Kế hoạch giao hàng', icon: <CarOutlined />, access: ['manager'] },
  { path: '/warehouse', label: 'Xuất kho', icon: <InboxOutlined />, access: ['warehouse_keeper'] },
  {
    path: '/master-data',
    label: 'Dữ liệu gốc',
    icon: <DatabaseOutlined />,
    access: ['company_admin', 'manager'],
  },
  { path: '/users', label: 'Người dùng', icon: <TeamOutlined />, access: ['company_admin'] },
  { path: '/companies', label: 'Công ty', icon: <ApartmentOutlined />, access: ['system'] },
]

export function AppLayout() {
  const { me, loading, logout, hasRole } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  if (loading) return <Spin fullscreen />
  if (!me) return <Navigate to="/login" replace />

  const items = NAV_ITEMS.filter((item) =>
    item.access.some((a) =>
      a === 'all' ? true : a === 'system' ? me.is_system_admin : hasRole(a),
    ),
  )

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Sider breakpoint="lg" collapsedWidth={0}>
        <Typography.Title level={4} style={{ color: '#fff', padding: '16px 24px', margin: 0 }}>
          TMS
        </Typography.Title>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={items.map((i) => ({ key: i.path, icon: i.icon, label: i.label }))}
          onClick={({ key }) => navigate(key)}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header
          style={{ background: '#fff', display: 'flex', justifyContent: 'flex-end', paddingInline: 16 }}
        >
          <Space>
            <Typography.Text>
              {me.full_name}
              {me.company && ` · ${me.company.name}`}
            </Typography.Text>
            <Button icon={<LogoutOutlined />} onClick={logout}>
              Đăng xuất
            </Button>
          </Space>
        </Layout.Header>
        <Layout.Content style={{ margin: 16 }}>
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  )
}
