import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Form, Input, Popconfirm, Segmented, Select, Space, Table, Tag } from 'antd'
import { useState } from 'react'

import { api } from '../api'
import { unwrap, usePaging } from '../lib/api-helpers'
import { useEntityModal } from '../lib/crud'
import {
  DEVICE_STATUS,
  DEVICE_TYPE,
  PAPER_SIZE,
  PRINTER_CONNECTION,
  fmtDateTime,
  options,
} from '../lib/labels'

type Device = components['schemas']['DeviceOut']
type DeviceForm = components['schemas']['DeviceCreate']
type DeviceType = components['schemas']['DeviceType']

export function DevicesPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const paging = usePaging()
  const [type, setType] = useState<DeviceType | 'ALL'>('ALL')
  const query = useQuery({
    queryKey: ['devices', paging.params, type],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/devices', {
          params: { query: { ...paging.params, device_type: type === 'ALL' ? undefined : type } },
        }),
      ),
  })
  const users = useQuery({
    queryKey: ['users'],
    queryFn: async () => unwrap(await api.GET('/api/v1/users')),
  })
  const warehouses = useQuery({
    queryKey: ['warehouses', 'all'],
    queryFn: async () => unwrap(await api.GET('/api/v1/warehouses', { params: { query: { limit: 500 } } })),
  })
  const userName = new Map(users.data?.map((u) => [u.id, u.full_name]))
  const warehouseName = new Map(warehouses.data?.items.map((w) => [w.id, w.name]))

  const setStatus = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: Device['status'] }) =>
      unwrap(
        await api.PATCH('/api/v1/devices/{device_id}', {
          params: { path: { device_id: id } },
          body: { status },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['devices'] }),
    onError: (e: Error) => message.error(e.message),
  })
  const remove = useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.DELETE('/api/v1/devices/{device_id}', { params: { path: { device_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['devices'] }),
    onError: (e: Error) => message.error(e.message),
  })

  const modal = useEntityModal<Device, DeviceForm>({
    queryKey: 'devices',
    title: 'thiết bị',
    defaults: { device_type: 'PRINTER', status: 'ACTIVE', connection: 'NETWORK', paper_size: 'A4' },
    save: async ({ device_type, ...values }, editing) =>
      editing
        ? unwrap(
            await api.PATCH('/api/v1/devices/{device_id}', {
              params: { path: { device_id: editing.id } },
              body: values,
            }),
          )
        : unwrap(await api.POST('/api/v1/devices', { body: { device_type, ...values } })),
  })

  return (
    <Card
      title="Thiết bị"
      extra={
        <Space>
          <Input.Search placeholder="Tìm tên, mã, model" allowClear onSearch={paging.search} />
          <Button type="primary" onClick={() => modal.show(null)}>
            Thêm thiết bị
          </Button>
        </Space>
      }
    >
      <Segmented
        style={{ marginBottom: 16 }}
        value={type}
        onChange={(v) => setType(v as DeviceType | 'ALL')}
        options={[{ value: 'ALL', label: 'Tất cả' }, ...options(DEVICE_TYPE)]}
      />
      <Table<Device>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data?.items}
        pagination={paging.pagination(query.data?.total)}
        scroll={{ x: 1000 }}
        columns={[
          { title: 'Tên thiết bị', dataIndex: 'name' },
          { title: 'Loại', dataIndex: 'device_type', width: 110, render: (v: DeviceType) => DEVICE_TYPE[v] },
          { title: 'Mã', dataIndex: 'identifier', width: 160, ellipsis: true },
          {
            title: 'Thông tin',
            render: (_, r) =>
              r.device_type === 'PRINTER'
                ? [r.connection && PRINTER_CONNECTION[r.connection], r.address, r.paper_size && PAPER_SIZE[r.paper_size]]
                    .filter(Boolean)
                    .join(' · ')
                : [r.model, r.os_version && `${r.platform ?? ''} ${r.os_version}`.trim(), r.app_version && `app ${r.app_version}`]
                    .filter(Boolean)
                    .join(' · '),
          },
          {
            title: 'Người dùng / Kho',
            render: (_, r) =>
              [r.user_id && userName.get(r.user_id), r.warehouse_id && warehouseName.get(r.warehouse_id)]
                .filter(Boolean)
                .join(' · '),
          },
          { title: 'Lần cuối', dataIndex: 'last_seen_at', width: 150, render: fmtDateTime },
          {
            title: 'Trạng thái',
            dataIndex: 'status',
            width: 110,
            render: (v: Device['status']) => <Tag color={DEVICE_STATUS[v].color}>{DEVICE_STATUS[v].label}</Tag>,
          },
          {
            title: '',
            width: 170,
            render: (_, r) => (
              <Space size="small">
                {r.status !== 'ACTIVE' && (
                  <a onClick={() => setStatus.mutate({ id: r.id, status: 'ACTIVE' })}>
                    {r.status === 'PENDING' ? 'Duyệt' : 'Mở khóa'}
                  </a>
                )}
                {r.status !== 'BLOCKED' && (
                  <a onClick={() => setStatus.mutate({ id: r.id, status: 'BLOCKED' })}>Khóa</a>
                )}
                <a onClick={() => modal.show(r)}>Sửa</a>
                <Popconfirm title="Xóa thiết bị này?" okText="Xóa" cancelText="Không" onConfirm={() => remove.mutate(r.id)}>
                  <a>Xóa</a>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      {modal.render((_, editing) => (
        <DeviceFields
          editing={editing}
          users={users.data?.map((u) => ({ value: u.id, label: `${u.full_name} (${u.username})` })) ?? []}
          warehouses={warehouses.data?.items.map((w) => ({ value: w.id, label: w.name })) ?? []}
        />
      ))}
    </Card>
  )
}

function DeviceFields({
  editing,
  users,
  warehouses,
}: {
  editing: Device | null
  users: { value: string; label: string }[]
  warehouses: { value: string; label: string }[]
}) {
  const type = Form.useWatch<DeviceType | undefined>('device_type', Form.useFormInstance())
  return (
    <>
      <Form.Item name="device_type" label="Loại thiết bị" rules={[{ required: true }]}>
        <Select
          disabled={Boolean(editing)}
          options={options(DEVICE_TYPE)}
          // Điện thoại tự đăng ký khi lái xe đăng nhập app.
          optionRender={(o) => (o.value === 'MOBILE' ? `${o.label} (thường tự đăng ký từ app)` : o.label)}
        />
      </Form.Item>
      <Form.Item name="name" label="Tên thiết bị" rules={[{ required: true }]}>
        <Input />
      </Form.Item>
      <Form.Item
        name="identifier"
        label={type === 'MOBILE' ? 'Mã cài đặt app' : 'Mã thiết bị / số serial'}
        extra={type === 'MOBILE' ? 'Do app sinh khi cài đặt, không nên sửa.' : undefined}
      >
        <Input disabled={type === 'MOBILE' && Boolean(editing)} />
      </Form.Item>
      <Form.Item name="status" label="Trạng thái" rules={[{ required: true }]}>
        <Select options={(Object.keys(DEVICE_STATUS) as Device['status'][]).map((v) => ({ value: v, label: DEVICE_STATUS[v].label }))} />
      </Form.Item>
      {type === 'PRINTER' && (
        <Space size="middle" wrap>
          <Form.Item name="connection" label="Kết nối">
            <Select style={{ width: 150 }} options={options(PRINTER_CONNECTION)} />
          </Form.Item>
          <Form.Item name="address" label="Địa chỉ (IP / cổng)">
            <Input style={{ width: 160 }} placeholder="192.168.1.50" />
          </Form.Item>
          <Form.Item name="paper_size" label="Khổ giấy">
            <Select style={{ width: 150 }} options={options(PAPER_SIZE)} />
          </Form.Item>
        </Space>
      )}
      <Form.Item name="warehouse_id" label="Đặt tại kho">
        <Select allowClear options={warehouses} />
      </Form.Item>
      {type !== 'PRINTER' && (
        <Form.Item name="user_id" label={type === 'MOBILE' ? 'Người dùng gần nhất' : 'Giao cho người dùng'}>
          <Select allowClear showSearch optionFilterProp="label" options={users} />
        </Form.Item>
      )}
      <Form.Item name="note" label="Ghi chú">
        <Input.TextArea rows={2} />
      </Form.Item>
    </>
  )
}
