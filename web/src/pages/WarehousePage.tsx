import { useQuery } from '@tanstack/react-query'
import { Card, DatePicker, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useNavigate, useSearchParams } from 'react-router'

import { api } from '../api'
import { unwrap } from '../lib/api-helpers'
import { TRIP_STATUS, fmtNumber } from '../lib/labels'
import { toISODate, type TripSummary } from '../lib/trips'

/** Thủ kho: lệnh đã duyệt cần soạn/xuất hàng và lệnh đã xuất trong ngày. */
export function WarehousePage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const planDate = params.get('date') ?? toISODate(dayjs())
  const query = useQuery({
    queryKey: ['trips', planDate, 'warehouse'],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/trips', {
          params: { query: { plan_date: planDate, order_status: ['APPROVED', 'PICKED', 'DISPATCHED', 'CLOSED'] } },
        }),
      ),
  })

  return (
    <Card
      title="Xuất kho"
      extra={
        <DatePicker
          allowClear={false}
          format="DD/MM/YYYY"
          value={dayjs(planDate)}
          onChange={(d) => d && setParams({ date: toISODate(d) })}
        />
      }
    >
      <Table<TripSummary>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data}
        pagination={false}
        scroll={{ x: 800 }}
        onRow={(t) => ({ onClick: () => navigate(`/trips/${t.id}`), style: { cursor: 'pointer' } })}
        columns={[
          { title: 'Mã lệnh', dataIndex: 'code', width: 120 },
          { title: 'Kho', dataIndex: 'warehouse_code', width: 80 },
          { title: 'Xe', render: (_, t) => `${t.vehicle_code} - ${t.vehicle_name}` },
          { title: 'Lái xe', render: (_, t) => t.driver?.full_name },
          { title: 'Điểm dừng', dataIndex: 'stop_count', width: 90, align: 'right' },
          { title: 'Kg', dataIndex: 'total_weight_kg', width: 100, align: 'right', render: fmtNumber },
          {
            title: 'Trạng thái',
            dataIndex: 'order_status',
            width: 130,
            render: (v: TripSummary['order_status']) =>
              v === 'APPROVED' ? <Tag color="orange">Chờ xuất kho</Tag> : <Tag color={TRIP_STATUS[v].color}>{TRIP_STATUS[v].label}</Tag>,
          },
        ]}
      />
    </Card>
  )
}
