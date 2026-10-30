import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Drawer,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
} from 'antd'
import type { Dayjs } from 'dayjs'
import { useState } from 'react'

import { api } from '../api'
import { useAuth } from '../auth-context'
import { unwrap, usePaging } from '../lib/api-helpers'
import {
  ORDER_STATUS,
  PART_STATUS,
  TEMP_GROUP,
  fmtDate,
  fmtNumber,
  options,
} from '../lib/labels'

type Order = components['schemas']['OrderOut']
type Part = components['schemas']['OrderPartOut']
type Line = components['schemas']['OrderLineOut']

const partTags = (parts: Part[]) =>
  parts.map((p) => (
    <Tag key={p.id} color={PART_STATUS[p.status].color}>
      {TEMP_GROUP[p.temp_group]} · {fmtNumber(p.weight_kg)} kg · {PART_STATUS[p.status].label}
    </Tag>
  ))

export function OrdersPage() {
  const paging = usePaging()
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [status, setStatus] = useState<Order['status']>()
  const [selected, setSelected] = useState<string>()

  const query = useQuery({
    queryKey: ['orders', paging.params, range?.map((d) => d?.format('YYYY-MM-DD')), status],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/orders', {
          params: {
            query: {
              ...paging.params,
              requested_from: range?.[0]?.format('YYYY-MM-DD'),
              requested_to: range?.[1]?.format('YYYY-MM-DD'),
              status,
            },
          },
        }),
      ),
  })

  return (
    <Card
      title="Đơn hàng"
      extra={
        <Space wrap>
          <DatePicker.RangePicker
            format="DD/MM/YYYY"
            placeholder={['Giao từ ngày', 'đến ngày']}
            onChange={(v) => setRange(v)}
          />
          <Select
            allowClear
            placeholder="Trạng thái"
            style={{ width: 140 }}
            value={status}
            onChange={setStatus}
            options={options(ORDER_STATUS)}
          />
          <Input.Search placeholder="Số đơn, mã/tên KH" allowClear onSearch={paging.search} />
        </Space>
      }
    >
      <Table<Order>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data?.items}
        pagination={paging.pagination(query.data?.total)}
        scroll={{ x: 1100 }}
        onRow={(r) => ({ onClick: () => setSelected(r.id), style: { cursor: 'pointer' } })}
        columns={[
          { title: 'Số đơn', dataIndex: 'external_ref', width: 130 },
          { title: 'Ngày giao YC', dataIndex: 'requested_date', width: 110, render: fmtDate },
          {
            title: 'Khách hàng',
            render: (_, o) => `${o.customer_code} - ${o.customer_name}`,
          },
          { title: 'Điểm giao', dataIndex: 'delivery_point_code', width: 90 },
          { title: 'Giá trị (đ)', dataIndex: 'order_value', width: 130, align: 'right', render: fmtNumber },
          { title: 'Phần đơn', render: (_, o) => partTags(o.parts) },
          {
            title: 'Trạng thái',
            dataIndex: 'status',
            width: 110,
            render: (v: Order['status']) => ORDER_STATUS[v],
          },
        ]}
      />
      <OrderDrawer orderId={selected} onClose={() => setSelected(undefined)} />
    </Card>
  )
}

function OrderDrawer({ orderId, onClose }: { orderId?: string; onClose: () => void }) {
  const { hasRole } = useAuth()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const detail = useQuery({
    queryKey: ['orders', 'detail', orderId],
    enabled: Boolean(orderId),
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/orders/{order_id}', { params: { path: { order_id: orderId! } } })),
  })
  const cancel = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST('/api/v1/orders/{order_id}/cancel', { params: { path: { order_id: orderId! } } })),
    onSuccess: async () => {
      message.success('Đã hủy đơn')
      await queryClient.invalidateQueries({ queryKey: ['orders'] })
    },
    onError: (e: Error) => message.error(e.message),
  })
  const order = detail.data
  const cancellable =
    order?.status === 'OPEN' && order.parts.every((p) => p.status === 'PENDING') && hasRole('company_admin', 'manager')

  return (
    <Drawer
      open={Boolean(orderId)}
      onClose={onClose}
      size="large"
      title={order ? `Đơn ${order.external_ref}` : 'Đơn hàng'}
      loading={detail.isLoading}
      extra={
        cancellable && (
          <Popconfirm title="Hủy đơn này?" okText="Hủy đơn" cancelText="Không" onConfirm={() => cancel.mutate()}>
            <Button danger loading={cancel.isPending}>
              Hủy đơn
            </Button>
          </Popconfirm>
        )
      }
    >
      {order && (
        <Space orientation="vertical" size="large" style={{ width: '100%' }}>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="Khách hàng">
              {order.customer_code} - {order.customer_name}
            </Descriptions.Item>
            <Descriptions.Item label="Điểm giao">
              {order.delivery_point_code} - {order.delivery_address}
            </Descriptions.Item>
            <Descriptions.Item label="Ngày đặt / giao YC">
              {fmtDate(order.order_date)} / {fmtDate(order.requested_date)}
            </Descriptions.Item>
            <Descriptions.Item label="Giá trị">{fmtNumber(order.order_value)} đ</Descriptions.Item>
            <Descriptions.Item label="Trạng thái">{ORDER_STATUS[order.status]}</Descriptions.Item>
            <Descriptions.Item label="Phần đơn">{partTags(order.parts)}</Descriptions.Item>
            {order.note && <Descriptions.Item label="Ghi chú">{order.note}</Descriptions.Item>}
          </Descriptions>
          <Table<Line>
            rowKey="line_no"
            size="small"
            pagination={false}
            dataSource={order.lines}
            columns={[
              { title: '#', dataIndex: 'line_no', width: 40 },
              { title: 'Mặt hàng', render: (_, l) => `${l.product_code} - ${l.product_name}` },
              { title: 'Nhóm', dataIndex: 'temp_group', width: 90, render: (v: Line['temp_group']) => TEMP_GROUP[v] },
              { title: 'SL', width: 90, align: 'right', render: (_, l) => `${fmtNumber(l.qty)} ${l.uom}` },
              { title: 'Kg', dataIndex: 'weight_kg', width: 80, align: 'right', render: fmtNumber },
              { title: 'Thành tiền', dataIndex: 'amount', width: 110, align: 'right', render: fmtNumber },
            ]}
          />
        </Space>
      )}
    </Drawer>
  )
}
