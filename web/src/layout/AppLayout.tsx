import {
  ApartmentOutlined,
  BarChartOutlined,
  CarOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  HomeOutlined,
  ImportOutlined,
  InboxOutlined,
  KeyOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MobileOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import type { CompanyRole } from '@tms/api-client'
import { Button, Layout, Menu, Space, Spin, Typography, type MenuProps } from 'antd'
import { useState, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router'

import { useAuth } from '../auth-context'
import { ChangePasswordModal } from './ChangePasswordModal'

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
  { path: '/reports', label: 'Báo cáo', icon: <BarChartOutlined />, access: ['manager', 'company_admin'] },
  { path: '/imports', label: 'Import dữ liệu', icon: <ImportOutlined />, access: ['company_admin', 'manager'] },
  { path: '/users', label: 'Người dùng', icon: <TeamOutlined />, access: ['company_admin'] },
  { path: '/devices', label: 'Thiết bị', icon: <MobileOutlined />, access: ['company_admin'] },
  { path: '/settings', label: 'Cấu hình', icon: <SettingOutlined />, access: ['company_admin'] },
  { path: '/companies', label: 'Công ty', icon: <ApartmentOutlined />, access: ['system'] },
]

const COLLAPSED_KEY = 'tms-sider-collapsed'

function savedCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === '1'
  } catch {
    return false
  }
}

export function AppLayout() {
  const { me, loading, logout, hasRole } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [changingPassword, setChangingPassword] = useState(false)
  // Màn hình rộng: thu gọn còn icon, nhớ lựa chọn. Màn hình hẹp: ẩn hẳn, chỉ mở khi bấm.
  const [collapsedWide, setCollapsedWide] = useState(savedCollapsed)
  const [narrow, setNarrow] = useState(false)
  const [openNarrow, setOpenNarrow] = useState(false)
  const collapsed = narrow ? !openNarrow : collapsedWide

  const toggleSider = () => {
    if (narrow) return setOpenNarrow(!openNarrow)
    setCollapsedWide(!collapsed)
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? '0' : '1')
    } catch {
      // Không lưu được thì chỉ mất ghi nhớ lựa chọn.
    }
  }

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
      <Layout.Sider
        breakpoint="lg"
        trigger={null}
        collapsible
        collapsed={collapsed}
        collapsedWidth={narrow ? 0 : 80}
        onBreakpoint={(broken) => {
          setNarrow(broken)
          setOpenNarrow(false)
        }}
      >
        <Typography.Title
          level={4}
          style={{ color: '#fff', padding: '16px 0', margin: 0, textAlign: 'center' }}
        >
          TMS
        </Typography.Title>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          defaultOpenKeys={openGroup ? [openGroup] : []}
          items={items}
          onClick={({ key }) => {
            navigate(key)
            setOpenNarrow(false)
          }}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header
          style={{
            background: '#fff',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            paddingInline: 16,
          }}
        >
          <Button
            type="text"
            aria-label={collapsed ? 'Mở rộng menu' : 'Thu gọn menu'}
            title={collapsed ? 'Mở rộng menu' : 'Thu gọn menu'}
            aria-expanded={!collapsed}
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={toggleSider}
          />
          <Space>
            <Typography.Text>
              {me.full_name}
              {me.company && ` · ${me.company.name}`}
            </Typography.Text>
            <Button icon={<KeyOutlined />} onClick={() => setChangingPassword(true)}>
              Đổi mật khẩu
            </Button>
            <Button icon={<LogoutOutlined />} onClick={logout}>
              Đăng xuất
            </Button>
          </Space>
        </Layout.Header>
        <Layout.Content style={{ margin: 16 }}>
          <Outlet />
        </Layout.Content>
        <ChangePasswordModal open={changingPassword} onClose={() => setChangingPassword(false)} />
      </Layout>
    </Layout>
  )
}
