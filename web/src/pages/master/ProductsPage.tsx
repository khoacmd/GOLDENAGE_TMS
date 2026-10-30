import type { components } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Form, Input, InputNumber, Select, Space, Switch, Table, Tag } from 'antd'

import { api } from '../../api'
import { useAuth } from '../../auth-context'
import { unwrap, usePaging } from '../../lib/api-helpers'
import { useEntityModal } from '../../lib/crud'
import { TEMP_CLASS, fmtNumber, options } from '../../lib/labels'

type Product = components['schemas']['ProductOut']
type ProductForm = components['schemas']['ProductCreate']

const TEMP_COLOR = { DRY: 'orange', CHILLED: 'cyan', FROZEN: 'blue' } as const

export function ProductsPage() {
  const { hasRole } = useAuth()
  const canEdit = hasRole('company_admin', 'manager')
  const paging = usePaging()
  const query = useQuery({
    queryKey: ['products', paging.params],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/products', { params: { query: paging.params } })),
  })

  const modal = useEntityModal<Product, ProductForm>({
    queryKey: 'products',
    title: 'mặt hàng',
    defaults: { is_active: true, temp_class: 'DRY' },
    save: async (values, editing) =>
      editing
        ? unwrap(
            await api.PATCH('/api/v1/products/{product_id}', {
              params: { path: { product_id: editing.id } },
              body: values,
            }),
          )
        : unwrap(await api.POST('/api/v1/products', { body: values })),
  })

  return (
    <Card
      title="Mặt hàng"
      extra={
        <Space>
          <Input.Search placeholder="Tìm mã, tên" allowClear onSearch={paging.search} />
          {canEdit && (
            <Button type="primary" onClick={() => modal.show(null)}>
              Thêm mặt hàng
            </Button>
          )}
        </Space>
      }
    >
      <Table<Product>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data?.items}
        pagination={paging.pagination(query.data?.total)}
        scroll={{ x: 700 }}
        columns={[
          { title: 'Mã', dataIndex: 'code', width: 150 },
          { title: 'Tên hàng', dataIndex: 'name' },
          {
            title: 'Loại',
            dataIndex: 'temp_class',
            width: 90,
            render: (v: Product['temp_class']) => <Tag color={TEMP_COLOR[v]}>{TEMP_CLASS[v]}</Tag>,
          },
          { title: 'ĐVT', dataIndex: 'uom', width: 90 },
          { title: 'Trọng lượng (kg)', dataIndex: 'weight_kg', width: 140, align: 'right', render: fmtNumber },
          {
            title: 'Trạng thái',
            dataIndex: 'is_active',
            width: 110,
            render: (v: boolean) => (v ? <Tag color="green">Hoạt động</Tag> : <Tag>Ngưng</Tag>),
          },
          ...(canEdit
            ? [{ title: '', width: 60, render: (_: unknown, r: Product) => <a onClick={() => modal.show(r)}>Sửa</a> }]
            : []),
        ]}
      />
      {modal.render((_, editing) => (
        <>
          <Form.Item name="code" label="Mã hàng" rules={[{ required: true }]}>
            <Input disabled={Boolean(editing)} />
          </Form.Item>
          <Form.Item name="name" label="Tên hàng" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Space size="large" wrap>
            <Form.Item name="temp_class" label="Loại hàng" rules={[{ required: true }]}>
              <Select style={{ width: 140 }} options={options(TEMP_CLASS)} />
            </Form.Item>
            <Form.Item name="uom" label="Đơn vị tính" rules={[{ required: true }]}>
              <Input style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="weight_kg" label="Trọng lượng/ĐVT (kg)" rules={[{ required: true }]}>
              <InputNumber min={0} step={0.1} stringMode style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Form.Item name="is_active" label="Hoạt động" valuePropName="checked">
            <Switch />
          </Form.Item>
        </>
      ))}
    </Card>
  )
}
