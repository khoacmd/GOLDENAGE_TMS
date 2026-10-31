import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag } from 'antd'
import { useState } from 'react'

import { api } from '../api'
import { unwrap } from '../lib/api-helpers'
import { useEntityModal } from '../lib/crud'
import { ROLE, options } from '../lib/labels'

type User = components['schemas']['CompanyUserOut']
type UserForm = components['schemas']['CompanyUserCreate'] & { is_active?: boolean }

/** Mã PIN chỉ dành cho tài khoản chỉ có vai trò lái xe (đăng nhập nhanh trên app). */
const pinAllowed = (u: User) => u.roles.length === 1 && u.roles[0] === 'driver'

/** Đặt / đổi mã PIN 6 số cho lái xe. */
function PinModal({ user, onClose }: { user: User | null; onClose: () => void }) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [pin, setPin] = useState('')
  const save = useMutation({
    mutationFn: async () =>
      unwrap(await api.PUT('/api/v1/users/{user_id}/pin', { params: { path: { user_id: user!.id } }, body: { pin } })),
    onSuccess: () => {
      message.success(`Đã đặt mã PIN cho ${user!.username}`)
      void queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
    onError: (e: Error) => message.error(e.message),
  })
  return (
    <Modal
      open={Boolean(user)}
      title={`${user?.has_pin ? 'Đổi' : 'Đặt'} mã PIN - ${user?.full_name ?? ''}`}
      okText="Lưu mã PIN"
      okButtonProps={{ disabled: !/^\d{6}$/.test(pin), loading: save.isPending }}
      onOk={() => save.mutate()}
      onCancel={onClose}
      afterOpenChange={(open) => !open && setPin('')}
      destroyOnHidden
    >
      <Space orientation="vertical" style={{ width: '100%' }}>
        <span>Lái xe đăng nhập app bằng tên đăng nhập <b>{user?.username}</b> và mã PIN 6 số. Không dùng dãy trùng hoặc liên tiếp (111111, 123456).</span>
        <Input.OTP length={6} mask value={pin} onChange={setPin} formatter={(v) => v.replace(/\D/g, '')} />
      </Space>
    </Modal>
  )
}

export function UsersPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [pinUser, setPinUser] = useState<User | null>(null)
  const clearPin = useMutation({
    mutationFn: async (u: User) => unwrap(await api.DELETE('/api/v1/users/{user_id}/pin', { params: { path: { user_id: u.id } } })),
    onSuccess: (u) => {
      message.success(`Đã xóa mã PIN của ${u.username}`)
      void queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (e: Error) => message.error(e.message),
  })
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
        scroll={{ x: 1000 }}
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
          {
            title: 'Mã PIN',
            width: 190,
            render: (_, r) =>
              pinAllowed(r) || r.has_pin ? (
                <Space size="small">
                  {r.has_pin ? <Tag color="blue">Đã đặt</Tag> : <Tag>Chưa đặt</Tag>}
                  {pinAllowed(r) && <a onClick={() => setPinUser(r)}>{r.has_pin ? 'Đổi' : 'Đặt'}</a>}
                  {r.has_pin && (
                    <Popconfirm title={`Xóa mã PIN của ${r.username}?`} onConfirm={() => clearPin.mutate(r)}>
                      <a>Xóa</a>
                    </Popconfirm>
                  )}
                </Space>
              ) : null,
          },
          { title: '', width: 60, render: (_, r) => <a onClick={() => modal.show(r)}>Sửa</a> },
        ]}
      />
      <PinModal user={pinUser} onClose={() => setPinUser(null)} />
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
