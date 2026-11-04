import type { components } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Button, Card, Form, Input, InputNumber, Select, Space, Switch, Table, Tag } from 'antd'

import { api } from '../../api'
import { useAuth } from '../../auth-context'
import { CODE_RULE, unwrap, usePaging } from '../../lib/api-helpers'
import { useEntityModal } from '../../lib/crud'
import { CARGO_CLASS, COST_METHOD, REGULATORY_CLASS, VEHICLE_TYPE, fmtNumber, options } from '../../lib/labels'
import { VehiclePermitsModal } from './VehiclePermits'

type Vehicle = components['schemas']['VehicleOut']
type VehicleForm = components['schemas']['VehicleCreate']

export function VehiclesPage() {
  const { hasRole } = useAuth()
  const canEdit = hasRole('company_admin')
  const paging = usePaging()
  const [permitsFor, setPermitsFor] = useState<Vehicle | null>(null)
  const query = useQuery({
    queryKey: ['vehicles', paging.params],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/vehicles', { params: { query: paging.params } })),
  })
  const warehouses = useQuery({
    queryKey: ['warehouses', 'all'],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/warehouses', { params: { query: { limit: 500 } } })),
  })
  const warehouseCode = new Map(warehouses.data?.items.map((w) => [w.id, w.code]))

  const modal = useEntityModal<Vehicle, VehicleForm>({
    queryKey: 'vehicles',
    title: 'xe',
    defaults: {
      is_active: true,
      vehicle_type: 'CAR',
      cargo_class: 'ANY',
      cost_allocation_method: 'WEIGHT',
      requires_assistant: false,
    },
    save: async (values, editing) =>
      editing
        ? unwrap(
            await api.PATCH('/api/v1/vehicles/{vehicle_id}', {
              params: { path: { vehicle_id: editing.id } },
              body: values,
            }),
          )
        : unwrap(await api.POST('/api/v1/vehicles', { body: values })),
  })

  return (
    <Card
      title="Đội xe"
      extra={
        <Space>
          <Input.Search placeholder="Tìm mã, tên, biển số" allowClear onSearch={paging.search} />
          {canEdit && (
            <Button type="primary" onClick={() => modal.show(null)}>
              Thêm xe
            </Button>
          )}
        </Space>
      }
    >
      <Table<Vehicle>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data?.items}
        pagination={paging.pagination(query.data?.total)}
        scroll={{ x: 1100 }}
        columns={[
          { title: 'Mã', dataIndex: 'code', width: 90 },
          { title: 'Tên xe', dataIndex: 'name' },
          { title: 'Biển số', dataIndex: 'plate_no', width: 120 },
          { title: 'Loại', dataIndex: 'vehicle_type', width: 90, render: (v: Vehicle['vehicle_type']) => VEHICLE_TYPE[v] },
          { title: 'Tải (kg)', dataIndex: 'capacity_kg', width: 100, align: 'right', render: fmtNumber },
          { title: 'Chi phí/km', dataIndex: 'cost_per_km', width: 110, align: 'right', render: fmtNumber },
          {
            title: 'Tổng TL (kg)',
            dataIndex: 'gross_weight_kg',
            width: 120,
            align: 'right',
            render: (v: Vehicle['gross_weight_kg'], r) =>
              r.regulatory_class !== 'VAN' ? '-' : v ? fmtNumber(v) : <Tag color="orange">Chưa khai</Tag>,
          },
          { title: 'Loại hàng', dataIndex: 'cargo_class', width: 150, render: (v: Vehicle['cargo_class']) => CARGO_CLASS[v] },
          { title: 'Phụ xe', dataIndex: 'requires_assistant', width: 80, render: (v: boolean) => (v ? 'Có' : '') },
          {
            title: 'Kho lấy hàng',
            dataIndex: 'warehouse_ids',
            render: (ids: string[]) => ids.map((id) => <Tag key={id}>{warehouseCode.get(id) ?? '?'}</Tag>),
          },
          {
            title: 'Trạng thái',
            dataIndex: 'is_active',
            width: 110,
            render: (v: boolean) => (v ? <Tag color="green">Hoạt động</Tag> : <Tag>Ngưng</Tag>),
          },
          {
            title: '',
            width: 110,
            render: (_: unknown, r: Vehicle) => (
              <Space>
                {r.vehicle_type === 'CAR' && <a onClick={() => setPermitsFor(r)}>Văn bản</a>}
                {canEdit && <a onClick={() => modal.show(r)}>Sửa</a>}
              </Space>
            ),
          },
        ]}
      />
      <VehiclePermitsModal vehicle={permitsFor} canEdit={canEdit} onClose={() => setPermitsFor(null)} />
      {modal.render((_, editing) => (
        <>
          <Space size="middle" wrap>
            <Form.Item name="code" label="Mã xe" rules={[{ required: true }, CODE_RULE]}>
              <Input disabled={Boolean(editing)} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="plate_no" label="Biển số" rules={[{ required: true }]}>
              <Input style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="vehicle_type" label="Loại xe" rules={[{ required: true }]}>
              <Select style={{ width: 140 }} options={options(VEHICLE_TYPE)} />
            </Form.Item>
          </Space>
          <Form.Item name="name" label="Tên xe" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Space size="middle" wrap>
            <Form.Item name="capacity_kg" label="Trọng tải (kg)" rules={[{ required: true }]}>
              <InputNumber min={1} stringMode style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="cost_per_km" label="Chi phí/km (đ)" rules={[{ required: true }]}>
              <InputNumber min={0} stringMode style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="requires_assistant" label="Cần phụ xe" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
          <Space size="middle" wrap align="start">
            <Form.Item
              name="gross_weight_kg"
              label="Tổng trọng lượng (kg)"
              extra="Xe + hàng theo đăng kiểm, bắt buộc với xe Van. Xe tải xét theo trọng tải ở trên."
              style={{ width: 280 }}
            >
              <InputNumber min={1} stringMode style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="regulatory_class" label="Phân loại lưu hành" extra="Trống = xe tải">
              <Select allowClear style={{ width: 160 }} options={options(REGULATORY_CLASS)} />
            </Form.Item>
          </Space>
          <Form.Item name="cargo_class" label="Loại hàng ưu tiên">
            <Select options={options(CARGO_CLASS)} />
          </Form.Item>
          <Form.Item name="cost_allocation_method" label="Phương pháp ghi nhận chi phí">
            <Select options={options(COST_METHOD)} />
          </Form.Item>
          <Form.Item name="warehouse_ids" label="Kho được lấy hàng" rules={[{ required: true }]}>
            <Select
              mode="multiple"
              options={warehouses.data?.items.map((w) => ({ value: w.id, label: `${w.code} - ${w.name}` }))}
            />
          </Form.Item>
          <Form.Item name="is_active" label="Hoạt động" valuePropName="checked">
            <Switch />
          </Form.Item>
        </>
      ), 640)}
    </Card>
  )
}
