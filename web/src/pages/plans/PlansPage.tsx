import { PlusOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, App, Button, Card, Checkbox, DatePicker, Modal, Progress, Space, Table, Tag } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { api } from '../../api'
import { useAuth } from '../../auth-context'
import { unwrap } from '../../lib/api-helpers'
import { DELIVERY_STATUS, TRIP_STATUS, fmtDateTime, fmtNumber } from '../../lib/labels'
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
  const { hasRole } = useAuth()
  const isManager = hasRole('manager')
  const runs = useQuery({
    queryKey: ['planning-runs', planDate],
    queryFn: async () => unwrap(await api.GET('/api/v1/planning/runs', { params: { query: { plan_date: planDate } } })),
  })
  const lastRun = runs.data?.[0]

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
          {isManager && <AutoPlanButton planDate={planDate} />}
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate(`/trips/new?date=${planDate}`)}>
            Lập lệnh giao
          </Button>
        </Space>
      }
    >
      {lastRun && (
        <Alert
          style={{ marginBottom: 16 }}
          type={lastRun.status === 'FAILED' ? 'error' : lastRun.unassigned.length ? 'warning' : 'info'}
          showIcon
          title={
            <span>
              Lập kế hoạch tự động lúc {fmtDateTime(lastRun.created_at)}
              {lastRun.status === 'SUCCEEDED'
                ? `: ${lastRun.summary.trips} chuyến, ${fmtNumber(lastRun.summary.distance_km)} km, ${lastRun.unassigned.length} phần đơn không xếp được. `
                : lastRun.status === 'FAILED'
                  ? ': lỗi. '
                  : ': đang chạy… '}
              <Link to={`/plans/runs/${lastRun.id}`}>Xem kết quả</Link>
            </span>
          }
        />
      )}
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
          {
            title: 'Mã lệnh',
            dataIndex: 'code',
            width: 140,
            render: (v: string, t) => (
              <Space size={4}>
                {v}
                {t.source === 'AUTO' && <Tag color="purple">Tự động</Tag>}
              </Space>
            ),
          },
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

function AutoPlanButton({ planDate }: { planDate: string }) {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [replace, setReplace] = useState(true)
  const run = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST('/api/v1/planning/runs', { body: { plan_date: planDate, replace_drafts: replace } })),
    onSuccess: (r) => navigate(`/plans/runs/${r.id}`),
    onError: (e: Error) => message.error(e.message),
  })
  return (
    <>
      <Button icon={<ThunderboltOutlined />} onClick={() => setOpen(true)}>
        Lập kế hoạch tự động
      </Button>
      <Modal
        open={open}
        title={`Lập kế hoạch tự động ngày ${dayjs(planDate).format('DD/MM/YYYY')}`}
        okText="Lập kế hoạch"
        cancelText="Hủy"
        confirmLoading={run.isPending}
        onOk={() => run.mutate()}
        onCancel={() => setOpen(false)}
      >
        <p>
          Xếp mọi phần đơn đang chờ (kể cả đơn giao thất bại trước đó) có ngày giao yêu cầu đến ngày này vào các
          chuyến, tối ưu quãng đường và chi phí. Kết quả là các lệnh nháp để bạn xem, chỉnh và duyệt.
        </p>
        <Checkbox checked={replace} onChange={(e) => setReplace(e.target.checked)}>
          Hủy các lệnh nháp đã lập tự động trước đó của ngày này rồi lập lại
        </Checkbox>
      </Modal>
    </>
  )
}
