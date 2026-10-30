import type { components } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Form, Input, Space, Switch, Table, Tag } from 'antd'

import { api } from '../../api'
import { useAuth } from '../../auth-context'
import { unwrap, usePaging } from '../../lib/api-helpers'
import { CoordinateFields } from '../../lib/CoordinateFields'
import { mapLink, useEntityModal } from '../../lib/crud'

type Warehouse = components['schemas']['WarehouseOut']
type WarehouseForm = components['schemas']['WarehouseCreate']

export function WarehousesPage() {
  const { hasRole } = useAuth()
  const canEdit = hasRole('company_admin')
  const paging = usePaging()
  const query = useQuery({
    queryKey: ['warehouses', paging.params],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/warehouses', { params: { query: paging.params } })),
  })

  const modal = useEntityModal<Warehouse, WarehouseForm>({
    queryKey: 'warehouses',
    title: 'kho',
    defaults: { is_active: true },
    save: async (values, editing) =>
      editing
        ? unwrap(
            await api.PATCH('/api/v1/warehouses/{warehouse_id}', {
              params: { path: { warehouse_id: editing.id } },
              body: values,
            }),
          )
        : unwrap(await api.POST('/api/v1/warehouses', { body: values })),
  })

  return (
    <Card
      title="Kho hàng"
      extra={
        <Space>
          <Input.Search placeholder="Tìm mã, tên" allowClear onSearch={paging.search} />
          {canEdit && (
            <Button type="primary" onClick={() => modal.show(null)}>
              Thêm kho
            </Button>
          )}
        </Space>
      }
    >
      <Table<Warehouse>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data?.items}
        pagination={paging.pagination(query.data?.total)}
        scroll={{ x: 800 }}
        onRow={(r) => ({ onDoubleClick: () => canEdit && modal.show(r) })}
        columns={[
          { title: 'Mã', dataIndex: 'code', width: 110 },
          { title: 'Tên kho', dataIndex: 'name' },
          { title: 'Địa chỉ', dataIndex: 'address' },
          {
            title: 'Tọa độ',
            render: (_, r) => (
              <a href={mapLink(r.latitude, r.longitude)} target="_blank" rel="noreferrer">
                {Number(r.latitude).toFixed(5)}, {Number(r.longitude).toFixed(5)}
              </a>
            ),
          },
          {
            title: 'Trạng thái',
            dataIndex: 'is_active',
            width: 120,
            render: (v: boolean) => (v ? <Tag color="green">Hoạt động</Tag> : <Tag>Ngưng</Tag>),
          },
          ...(canEdit
            ? [{ title: '', width: 70, render: (_: unknown, r: Warehouse) => <a onClick={() => modal.show(r)}>Sửa</a> }]
            : []),
        ]}
      />
      {modal.render((_, editing) => (
        <>
          <Form.Item name="code" label="Mã kho" rules={[{ required: true }]}>
            <Input disabled={Boolean(editing)} />
          </Form.Item>
          <Form.Item name="name" label="Tên kho" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="address" label="Địa chỉ" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <CoordinateFields />
          <Form.Item name="is_active" label="Hoạt động" valuePropName="checked">
            <Switch />
          </Form.Item>
        </>
      ))}
    </Card>
  )
}
