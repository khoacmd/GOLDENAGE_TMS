import {
  ApartmentOutlined,
  CarOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  HomeOutlined,
  ImportOutlined,
  InboxOutlined,
  LogoutOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import type { CompanyRole } from '@tms/api-client'
import { Button, Layout, Menu, Space, Spin, Typography, type MenuProps } from 'antd'
import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router'

import { useAuth } from '../auth-context'

interface NavItem {
  path: string
  label: string
  icon?: ReactNode
  /** Vai trò trong công ty được thấy menu; `system` = admin hệ thống. */
  access: Access[]
  children?: NavItem[]
}

type Access = CompanyRole | 'system' | 'all'

type MenuItem = Required<MenuProps>['items'][number]

const OFFICE: Access[] = ['company_admin', 'manager', 'warehouse_keeper']

const NAV_ITEMS: NavItem[] = [
  { path: '/', label: 'Tổng quan', icon: <HomeOutlined />, access: ['all'] },
  { path: '/orders', label: 'Đơn hàng', icon: <FileTextOutlined />, access: OFFICE },
  { path: '/plans', label: 'Kế hoạch giao hàng', icon: <CarOutlined />, access: ['manager', 'company_admin'] },
  { path: '/warehouse', label: 'Xuất kho', icon: <InboxOutlined />, access: ['warehouse_keeper'] },
  {
    path: '/master-data',
    label: 'Dữ liệu gốc',
    icon: <DatabaseOutlined />,
    access: OFFICE,
    children: [
      { path: '/master-data/customers', label: 'Khách hàng', access: OFFICE },
      { path: '/master-data/products', label: 'Mặt hàng', access: OFFICE },
      { path: '/master-data/inventory', label: 'Tồn kho', access: OFFICE },
      { path: '/master-data/warehouses', label: 'Kho hàng', access: OFFICE },
      { path: '/master-data/vehicles', label: 'Đội xe', access: OFFICE },
    ],
  },
  { path: '/imports', label: 'Import dữ liệu', icon: <ImportOutlined />, access: ['company_admin', 'manager'] },
  { path: '/users', label: 'Người dùng', icon: <TeamOutlined />, access: ['company_admin'] },
  { path: '/settings', label: 'Cấu hình', icon: <SettingOutlined />, access: ['company_admin'] },
  { path: '/companies', label: 'Công ty', icon: <ApartmentOutlined />, access: ['system'] },
]

export function AppLayout() {
  const { me, loading, logout, hasRole } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  if (loading) return <Spin fullscreen />
  if (!me) return <Navigate to="/login" replace />

  const allowed = (item: NavItem) =>
    item.access.some((a) => (a === 'all' ? true : a === 'system' ? me.is_system_admin : hasRole(a)))
  const toMenu = (item: NavItem): MenuItem => ({
    key: item.path,
    icon: item.icon,
    label: item.label,
    children: item.children?.filter(allowed).map(toMenu),
  })
  const items = NAV_ITEMS.filter(allowed).map(toMenu)
  const openGroup = NAV_ITEMS.find((i) => i.children && location.pathname.startsWith(i.path))?.path

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
          defaultOpenKeys={openGroup ? [openGroup] : []}
          items={items}
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
