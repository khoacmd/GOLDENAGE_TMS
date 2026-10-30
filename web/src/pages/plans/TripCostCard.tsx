import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Descriptions, Form, Input, InputNumber, Modal, Space, Table, Tag } from 'antd'
import { useState } from 'react'

import { api } from '../../api'
import { useAuth } from '../../auth-context'
import { unwrap } from '../../lib/api-helpers'
import { COST_METHOD, fmtDateTime, fmtNumber } from '../../lib/labels'
import type { Trip } from '../../lib/trips'

type Cost = components['schemas']['TripCostOut']
type CostForm = components['schemas']['TripCostIn']
type Allocation = components['schemas']['AllocationOut']

const SOURCE: Record<Cost['distance_source'], string> = {
  ODOMETER: 'Theo công-tơ-mét',
  MANUAL: 'Nhập số km',
  PLANNED: 'Km kế hoạch',
  ESTIMATE: 'Ước lượng theo tuyến',
}
const money = (v: number | string) => `${fmtNumber(v)} đ`

/** Chi phí thực tế của chuyến (sau khi xuất phát) và phân bổ về từng đơn. */
export function TripCostCard({ trip }: { trip: Trip }) {
  const { message } = App.useApp()
  const { hasRole } = useAuth()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<CostForm>()
  const [open, setOpen] = useState(false)
  const query = useQuery({
    queryKey: ['trip-cost', trip.id],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/trips/{trip_id}/cost', { params: { path: { trip_id: trip.id } } })),
  })
  const save = useMutation({
    mutationFn: async (body: CostForm) =>
      unwrap(await api.PUT('/api/v1/trips/{trip_id}/cost', { params: { path: { trip_id: trip.id } }, body })),
    onSuccess: async () => {
      message.success('Đã ghi nhận chi phí chuyến')
      setOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['trip-cost', trip.id] })
    },
    onError: (e: Error) => message.error(e.message),
  })
  const cost = query.data
  const canEdit = hasRole('manager')

  const edit = () => {
    form.resetFields()
    form.setFieldsValue({
      odometer_start: cost?.odometer_start ?? undefined,
      odometer_end: cost?.odometer_end ?? undefined,
      distance_km: cost?.distance_source === 'MANUAL' ? cost.distance_km : undefined,
      extra_cost: cost?.extra_cost ?? 0,
      note: cost?.note ?? undefined,
    })
    setOpen(true)
  }

  return (
    <Card
      title="Chi phí chuyến"
      style={{ marginBottom: 16 }}
      loading={query.isLoading}
      extra={
        canEdit && (
          <Button size="small" onClick={edit}>
            {cost ? 'Sửa' : 'Ghi nhận km & chi phí'}
          </Button>
        )
      }
    >
      {!cost ? (
        <span style={{ color: '#888' }}>
          Chưa ghi nhận. Khi kết thúc chuyến, hệ thống tự tính theo km kế hoạch / ước lượng nếu chưa nhập.
        </span>
      ) : (
        <>
          <Descriptions size="small" column={2}>
            <Descriptions.Item label="Quãng đường">
              {fmtNumber(cost.distance_km)} km <Tag style={{ marginLeft: 4 }}>{SOURCE[cost.distance_source]}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Đơn giá">{money(cost.cost_per_km)}/km</Descriptions.Item>
            <Descriptions.Item label="Chi phí km">{money(cost.distance_cost)}</Descriptions.Item>
            <Descriptions.Item label="Phát sinh">{money(cost.extra_cost)}</Descriptions.Item>
            <Descriptions.Item label="Tổng chi phí">
              <b>{money(cost.total_cost)}</b>
            </Descriptions.Item>
            <Descriptions.Item label="Phân bổ theo">{COST_METHOD[cost.allocation_method]}</Descriptions.Item>
            {cost.note && <Descriptions.Item label="Ghi chú">{cost.note}</Descriptions.Item>}
            <Descriptions.Item label="Ghi nhận lúc">{fmtDateTime(cost.recorded_at)}</Descriptions.Item>
          </Descriptions>
          <Table<Allocation>
            rowKey="trip_item_id"
            size="small"
            pagination={false}
            dataSource={cost.allocations}
            columns={[
              { title: 'Đơn', dataIndex: 'external_ref' },
              { title: 'Khách hàng', dataIndex: 'customer_code' },
              { title: 'Khối lượng', dataIndex: 'weight_kg', align: 'right', render: (v: string) => `${fmtNumber(v)} kg` },
              { title: 'Chi phí phân bổ', dataIndex: 'amount', align: 'right', render: money },
            ]}
          />
        </>
      )}
      <Modal
        open={open}
        title={`Chi phí chuyến ${trip.code}`}
        okText="Lưu"
        cancelText="Hủy"
        confirmLoading={save.isPending}
        onOk={() => form.submit()}
        onCancel={() => setOpen(false)}
        forceRender
      >
        <Form<CostForm> form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Space size="middle" wrap>
            <Form.Item name="odometer_start" label="Công-tơ-mét lúc đi (km)">
              <InputNumber min={0} step={0.1} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="odometer_end" label="Công-tơ-mét lúc về (km)">
              <InputNumber min={0} step={0.1} style={{ width: 180 }} />
            </Form.Item>
          </Space>
          <Form.Item
            name="distance_km"
            label="Hoặc nhập số km đã chạy"
            extra="Ưu tiên số công-tơ-mét; để trống cả hai thì dùng km kế hoạch / ước lượng."
          >
            <InputNumber min={0} step={0.1} style={{ width: 180 }} />
          </Form.Item>
          <Form.Item name="extra_cost" label="Chi phí phát sinh (cầu đường, bến bãi…) (đ)">
            <InputNumber min={0} step={10000} style={{ width: 220 }} />
          </Form.Item>
          <Form.Item name="note" label="Ghi chú">
            <Input.TextArea rows={2} maxLength={500} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
