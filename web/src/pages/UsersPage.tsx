import type { components } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Form, Input, Select, Switch, Table, Tag } from 'antd'

import { api } from '../api'
import { unwrap } from '../lib/api-helpers'
import { useEntityModal } from '../lib/crud'
import { ROLE, options } from '../lib/labels'

type User = components['schemas']['CompanyUserOut']
type UserForm = components['schemas']['CompanyUserCreate'] & { is_active?: boolean }

export function UsersPage() {
  const query = useQuery({
    queryKey: ['users'],
    queryFn: async () => unwrap(await api.GET('/api/v1/users')),
  })

  const modal = useEntityModal<User, UserForm>({
    queryKey: 'users',
    title: 'người dùng',
    defaults: { roles: ['driver'] },
    save: async ({ roles, password, is_active, ...profile }, editing) => {
      if (!editing) return unwrap(await api.POST('/api/v1/users', { body: { ...profile, password, roles } }))
      const path = { params: { path: { user_id: editing.id } } }
      await unwrap(
        await api.PATCH('/api/v1/users/{user_id}', {
          ...path,
          body: { full_name: profile.full_name, email: profile.email, phone: profile.phone, is_active, ...(password ? { password } : {}) },
        }),
      )
      return unwrap(await api.PUT('/api/v1/users/{user_id}/roles', { ...path, body: { roles } }))
    },
  })

  return (
    <Card
      title="Người dùng"
      extra={
        <Button type="primary" onClick={() => modal.show(null)}>
          Thêm người dùng
        </Button>
      }
    >
      <Table<User>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data}
        pagination={false}
        scroll={{ x: 800 }}
        columns={[
          { title: 'Tên đăng nhập', dataIndex: 'username', width: 150 },
          { title: 'Họ tên', dataIndex: 'full_name' },
          { title: 'Điện thoại', dataIndex: 'phone', width: 130 },
          {
            title: 'Vai trò',
            dataIndex: 'roles',
            render: (roles: User['roles']) => roles.map((r) => <Tag key={r}>{ROLE[r]}</Tag>),
          },
          {
            title: 'Trạng thái',
            dataIndex: 'is_active',
            width: 110,
            render: (v: boolean) => (v ? <Tag color="green">Hoạt động</Tag> : <Tag>Đã khóa</Tag>),
          },
          { title: '', width: 60, render: (_, r) => <a onClick={() => modal.show(r)}>Sửa</a> },
        ]}
      />
      {modal.render((_, editing) => (
        <>
          <Form.Item
            name="username"
            label="Tên đăng nhập"
            rules={[{ required: true }, { pattern: /^[A-Za-z0-9._-]{3,64}$/, message: 'Chữ không dấu, số, . _ -' }]}
          >
            <Input disabled={Boolean(editing)} autoComplete="off" />
          </Form.Item>
          <Form.Item name="full_name" label="Họ tên" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="Điện thoại">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="Email" rules={[{ type: 'email' }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="password"
            label={editing ? 'Mật khẩu mới (bỏ trống nếu không đổi)' : 'Mật khẩu'}
            rules={[{ required: !editing }, { min: 8, message: 'Tối thiểu 8 ký tự' }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="roles" label="Vai trò" rules={[{ required: true }]}>
            <Select mode="multiple" options={options(ROLE)} />
          </Form.Item>
          {editing && (
            <Form.Item name="is_active" label="Hoạt động" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </>
      ))}
    </Card>
  )
}
