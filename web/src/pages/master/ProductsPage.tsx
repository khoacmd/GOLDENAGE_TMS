import type { components } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { AutoComplete, Button, Card, Form, Input, InputNumber, Select, Space, Switch, Table, Tag, Typography } from 'antd'

import { api } from '../../api'
import { useAuth } from '../../auth-context'
import { CODE_RULE, unwrap, usePaging } from '../../lib/api-helpers'
import { useEntityModal } from '../../lib/crud'
import { TEMP_CLASS, fmtNumber, options } from '../../lib/labels'

type Product = components['schemas']['ProductOut']
type ProductForm = components['schemas']['ProductCreate']

const TEMP_COLOR = { DRY: 'orange', CHILLED: 'cyan', FROZEN: 'blue' } as const

export function ProductsPage() {
  const { hasRole } = useAuth()
  const canEdit = hasRole('company_admin', 'manager')
  const paging = usePaging()
  const [filters, setFilters] = useState<{ factory?: string; product_group?: string }>({})
  const query = useQuery({
    queryKey: ['products', paging.params, filters],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/products', { params: { query: { ...paging.params, ...filters } } })),
  })
  // Nằm dưới khóa 'products' để được làm mới cùng danh sách sau khi lưu.
  const attributes = useQuery({
    queryKey: ['products', 'attributes'],
    queryFn: async () => unwrap(await api.GET('/api/v1/products/attributes')),
  })
  const toOptions = (values: string[] | undefined) => (values ?? []).map((v) => ({ value: v, label: v }))
  const factories = toOptions(attributes.data?.factories)
  const groups = toOptions(attributes.data?.product_groups)
  const filter = (key: keyof typeof filters) => (value: string | undefined) => {
    setFilters((f) => ({ ...f, [key]: value }))
    paging.reset()
  }

  const modal = useEntityModal<Product, ProductForm>({
    queryKey: 'products',
    title: 'mặt hàng',
    defaults: { is_active: true, temp_class: 'DRY', sku_ratio: '1', uom_ratio: '1' },
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
        <Space wrap>
          <Select
            allowClear
            placeholder="Nhà máy"
            style={{ width: 150 }}
            options={factories}
            value={filters.factory}
            onChange={filter('factory')}
          />
          <Select
            allowClear
            placeholder="Nhóm sản phẩm"
            style={{ width: 170 }}
            options={groups}
            value={filters.product_group}
            onChange={filter('product_group')}
          />
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
        scroll={{ x: 1200 }}
        columns={[
          { title: 'Mã', dataIndex: 'code', width: 150 },
          { title: 'Tên hàng', dataIndex: 'name', width: 280 },
          {
            title: 'Loại',
            dataIndex: 'temp_class',
            width: 90,
            render: (v: Product['temp_class']) => <Tag color={TEMP_COLOR[v]}>{TEMP_CLASS[v]}</Tag>,
          },
          { title: 'Nhà máy', dataIndex: 'factory', width: 120 },
          { title: 'Nhóm sản phẩm', dataIndex: 'product_group', width: 140 },
          { title: 'ĐVT', dataIndex: 'uom', width: 90 },
          { title: 'Trọng lượng (kg)', dataIndex: 'weight_kg', width: 140, align: 'right', render: fmtNumber },
          { title: 'SKU', dataIndex: 'sku_uom', width: 90 },
          {
            title: 'Quy đổi',
            width: 170,
            render: (_, p) =>
              p.sku_uom === p.uom ? '-' : `${fmtNumber(p.sku_ratio)} ${p.sku_uom} = ${fmtNumber(p.uom_ratio)} ${p.uom}`,
          },
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
          <Form.Item name="code" label="Mã hàng" rules={[{ required: true }, CODE_RULE]}>
            <Input disabled={Boolean(editing)} />
          </Form.Item>
          <Form.Item name="name" label="Tên hàng" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Space size="large" wrap>
            <Form.Item name="factory" label="Nhà máy">
              <AutoComplete style={{ width: 200 }} options={factories} filterOption allowClear />
            </Form.Item>
            <Form.Item name="product_group" label="Nhóm sản phẩm">
              <AutoComplete style={{ width: 200 }} options={groups} filterOption allowClear />
            </Form.Item>
          </Space>
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
          <Space size="large" wrap align="start">
            <Form.Item name="sku_uom" label="Đơn vị SKU" rules={[{ required: true }]}>
              <Input style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="sku_ratio" label="Số lượng SKU" rules={[{ required: true }]}>
              <InputNumber min={0.001} stringMode style={{ width: 120 }} />
            </Form.Item>
            <Form.Item name="uom_ratio" label="Bằng số lượng ĐVT" rules={[{ required: true }]}>
              <InputNumber min={0.001} stringMode style={{ width: 140 }} />
            </Form.Item>
          </Space>
          <Typography.Paragraph type="secondary">
            SKU là đơn vị trên đơn hàng và tồn kho. Ví dụ 48 Hộp = 1 Thùng: SKU là Hộp, nhập 48 và 1.
          </Typography.Paragraph>
          <Form.Item name="is_active" label="Hoạt động" valuePropName="checked">
            <Switch />
          </Form.Item>
        </>
      ))}
    </Card>
  )
}
