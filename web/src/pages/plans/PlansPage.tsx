import { PlusOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, DatePicker, Progress, Space, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useNavigate, useSearchParams } from 'react-router'

import { api } from '../../api'
import { unwrap } from '../../lib/api-helpers'
import { DELIVERY_STATUS, TRIP_STATUS, fmtNumber } from '../../lib/labels'
import { defaultPlanDate, loadPercent, toISODate, type TripSummary } from '../../lib/trips'

export function PlansPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const planDate = params.get('date') ?? defaultPlanDate()

  const trips = useQuery({
    queryKey: ['trips', planDate],
    queryFn: async () => unwrap(await api.GET('/api/v1/trips', { params: { query: { plan_date: planDate } } })),
  })
  const pending = useQuery({
    queryKey: ['available-parts', planDate],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/trips/available-parts', { params: { query: { plan_date: planDate } } })),
  })
  const active = trips.data?.filter((t) => t.order_status !== 'CANCELLED') ?? []

  return (
    <Card
      title="Kế hoạch giao hàng"
      extra={
        <Space wrap>
          <DatePicker
            allowClear={false}
            format="DD/MM/YYYY"
            value={dayjs(planDate)}
            onChange={(d) => d && setParams({ date: toISODate(d) })}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate(`/trips/new?date=${planDate}`)}>
            Lập lệnh giao
          </Button>
        </Space>
      }
    >
      <Space size="large" style={{ marginBottom: 16 }} wrap>
        <span>
          Lệnh: <b>{active.length}</b>
        </span>
        <span>
          Tổng khối lượng: <b>{fmtNumber(active.reduce((s, t) => s + Number(t.total_weight_kg), 0))} kg</b>
        </span>
        <span>
          Phần đơn chờ xếp lệnh:{' '}
          <Tag color={pending.data?.length ? 'orange' : 'green'}>{pending.data?.length ?? '…'}</Tag>
        </span>
      </Space>
      <Table<TripSummary>
        rowKey="id"
        loading={trips.isLoading}
        dataSource={trips.data}
        pagination={false}
        scroll={{ x: 1100 }}
        onRow={(t) => ({ onClick: () => navigate(`/trips/${t.id}`), style: { cursor: 'pointer' } })}
        columns={[
          { title: 'Mã lệnh', dataIndex: 'code', width: 120 },
          { title: 'Xe', width: 170, render: (_, t) => `${t.vehicle_code} · lượt ${t.trip_seq}` },
          { title: 'Kho', dataIndex: 'warehouse_code', width: 80 },
          { title: 'Lái xe', render: (_, t) => t.driver?.full_name ?? <Tag color="orange">Chưa phân công</Tag> },
          { title: 'Phụ xe', render: (_, t) => t.assistant?.full_name },
          { title: 'Điểm dừng', dataIndex: 'stop_count', width: 90, align: 'right' },
          {
            title: 'Tải',
            width: 170,
            render: (_, t) => (
              <Progress
                percent={loadPercent(t.total_weight_kg, t.capacity_kg)}
                size="small"
                format={() => `${fmtNumber(t.total_weight_kg)} kg`}
              />
            ),
          },
          {
            title: 'Lệnh',
            dataIndex: 'order_status',
            width: 110,
            render: (v: TripSummary['order_status']) => <Tag color={TRIP_STATUS[v].color}>{TRIP_STATUS[v].label}</Tag>,
          },
          {
            title: 'Giao hàng',
            dataIndex: 'delivery_status',
            width: 110,
            render: (v: TripSummary['delivery_status']) => (
              <Tag color={DELIVERY_STATUS[v].color}>{DELIVERY_STATUS[v].label}</Tag>
            ),
          },
        ]}
      />
    </Card>
  )
}
