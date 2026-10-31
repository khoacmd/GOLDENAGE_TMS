import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, DatePicker, Popconfirm, Segmented, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { api } from '../api'
import { unwrap } from '../lib/api-helpers'
import { TRIP_STATUS, fmtNumber } from '../lib/labels'
import { toISODate, type TripSummary } from '../lib/trips'

type Status = TripSummary['order_status']

/** Nhãn theo góc nhìn thủ kho: việc cần làm tiếp theo của lệnh. */
const KEEPER_STATUS: Partial<Record<Status, { label: string; color: string }>> = {
  APPROVED: { label: 'Chờ soạn hàng', color: 'orange' },
  PREPARED: { label: 'Đã soạn, chờ xuất kho', color: 'geekblue' },
}

const FILTERS: Record<string, Status[]> = {
  todo: ['APPROVED', 'PREPARED'],
  all: ['APPROVED', 'PREPARED', 'PICKED', 'DISPATCHED', 'CLOSED'],
}

/** Thủ kho: lệnh đã duyệt cần soạn hàng → xác nhận soạn xong → xác nhận xuất kho. */
export function WarehousePage() {
  const navigate = useNavigate()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [filter, setFilter] = useState<keyof typeof FILTERS>('all')
  const planDate = params.get('date') ?? toISODate(dayjs())
  const query = useQuery({
    queryKey: ['trips', planDate, 'warehouse', filter],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/trips', {
          params: { query: { plan_date: planDate, order_status: FILTERS[filter] } },
        }),
      ),
  })
  const action = useMutation({
    mutationFn: async ({ trip, step }: { trip: TripSummary; step: 'prepare' | 'pick' }) => {
      const path = { params: { path: { trip_id: trip.id } } }
      return unwrap(
        step === 'prepare'
          ? await api.POST('/api/v1/trips/{trip_id}/prepare', path)
          : await api.POST('/api/v1/trips/{trip_id}/pick', path),
      )
    },
    onSuccess: (t) => {
      message.success(`Lệnh ${t.code}: ${TRIP_STATUS[t.order_status].label.toLowerCase()}`)
      void queryClient.invalidateQueries({ queryKey: ['trips'] })
      void queryClient.invalidateQueries({ queryKey: ['trip', t.id] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  return (
    <Card
      title="Xuất kho"
      extra={
        <>
          <Segmented
            style={{ marginRight: 8 }}
            value={filter}
            onChange={(v) => setFilter(v as keyof typeof FILTERS)}
            options={[
              { value: 'todo', label: 'Cần xử lý' },
              { value: 'all', label: 'Tất cả' },
            ]}
          />
          <DatePicker
            allowClear={false}
            format="DD/MM/YYYY"
            value={dayjs(planDate)}
            onChange={(d) => d && setParams({ date: toISODate(d) })}
          />
        </>
      }
    >
      <Table<TripSummary>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data}
        pagination={false}
        scroll={{ x: 960 }}
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
            width: 170,
            render: (v: Status) => {
              const st = KEEPER_STATUS[v] ?? TRIP_STATUS[v]
              return <Tag color={st.color}>{st.label}</Tag>
            },
          },
          {
            title: 'Thao tác',
            width: 170,
            render: (_, t) => {
              const step = t.order_status === 'APPROVED' ? 'prepare' : t.order_status === 'PREPARED' ? 'pick' : null
              if (!step) return null
              return (
                // Không mở chi tiết lệnh khi bấm nút / hộp xác nhận.
                <span onClick={(e) => e.stopPropagation()}>
                  <Popconfirm
                    title={step === 'prepare' ? 'Xác nhận đã soạn đủ hàng theo phiếu soạn hàng?' : 'Xác nhận đã giao đủ hàng lên xe (xuất kho)?'}
                    onConfirm={() => action.mutate({ trip: t, step })}
                  >
                    <Button size="small" type={step === 'prepare' ? 'default' : 'primary'} loading={action.isPending && action.variables.trip.id === t.id}>
                      {step === 'prepare' ? 'Xác nhận soạn hàng' : 'Xác nhận xuất kho'}
                    </Button>
                  </Popconfirm>
                </span>
              )
            },
          },
        ]}
      />
    </Card>
  )
}
