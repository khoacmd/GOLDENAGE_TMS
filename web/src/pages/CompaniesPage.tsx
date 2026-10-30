import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Divider, Form, Input, Popconfirm, Table, Tag } from 'antd'

import { api } from '../api'
import { unwrap } from '../lib/api-helpers'
import { useEntityModal } from '../lib/crud'
import { fmtDateTime } from '../lib/labels'

type Company = components['schemas']['CompanyOut']
type CompanyForm = components['schemas']['CompanyCreate']

export function CompaniesPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['companies'],
    queryFn: async () => unwrap(await api.GET('/api/v1/admin/companies')),
  })
  const modal = useEntityModal<Company, CompanyForm>({
    queryKey: 'companies',
    title: 'công ty',
    save: async (values, editing) =>
      editing
        ? unwrap(
            await api.PATCH('/api/v1/admin/companies/{company_id}', {
              params: { path: { company_id: editing.id } },
              body: { name: values.name },
            }),
          )
        : unwrap(await api.POST('/api/v1/admin/companies', { body: values })),
  })
  const toggle = useMutation({
    mutationFn: async (c: Company) =>
      unwrap(
        await api.PATCH('/api/v1/admin/companies/{company_id}', {
          params: { path: { company_id: c.id } },
          body: { is_active: !c.is_active },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['companies'] }),
    onError: (e: Error) => message.error(e.message),
  })

  return (
    <Card
      title="Công ty"
      extra={
        <Button type="primary" onClick={() => modal.show(null)}>
          Mở công ty mới
        </Button>
      }
    >
      <Table<Company>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data}
        pagination={false}
        columns={[
          { title: 'Mã', dataIndex: 'code', width: 120 },
          { title: 'Tên công ty', dataIndex: 'name' },
          { title: 'Ngày tạo', dataIndex: 'created_at', width: 180, render: fmtDateTime },
          {
            title: 'Trạng thái',
            dataIndex: 'is_active',
            width: 120,
            render: (v: boolean) => (v ? <Tag color="green">Hoạt động</Tag> : <Tag color="red">Đã đóng</Tag>),
          },
          {
            title: '',
            width: 150,
            render: (_, c) => (
              <>
                <a onClick={() => modal.show(c)}>Sửa</a>
                <Divider orientation="vertical" />
                <Popconfirm
                  title={c.is_active ? 'Đóng công ty? Mọi người dùng sẽ không truy cập được.' : 'Mở lại công ty?'}
                  onConfirm={() => toggle.mutate(c)}
                >
                  <a>{c.is_active ? 'Đóng' : 'Mở lại'}</a>
                </Popconfirm>
              </>
            ),
          },
        ]}
      />
      {modal.render((_, editing) => (
        <>
          <Form.Item name="code" label="Mã công ty" rules={[{ required: true }, { pattern: /^[A-Za-z0-9_-]{2,32}$/ }]}>
            <Input disabled={Boolean(editing)} />
          </Form.Item>
          <Form.Item name="name" label="Tên công ty" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          {!editing && (
            <>
              <Divider titlePlacement="start">Admin công ty</Divider>
              <Form.Item
                name={['admin', 'username']}
                label="Tên đăng nhập"
                extra="Nếu tài khoản đã tồn tại sẽ được gán làm admin công ty mới."
                rules={[{ required: true }]}
              >
                <Input autoComplete="off" />
              </Form.Item>
              <Form.Item name={['admin', 'full_name']} label="Họ tên">
                <Input />
              </Form.Item>
              <Form.Item name={['admin', 'password']} label="Mật khẩu" rules={[{ min: 8 }]}>
                <Input.Password autoComplete="new-password" />
              </Form.Item>
            </>
          )}
        </>
      ))}
    </Card>
  )
}
