import type { components } from '@tms/api-client'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Empty,
  Progress,
  Result,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd'
import { useState, type DragEvent } from 'react'
import { useNavigate, useParams } from 'react-router'

import { api } from '../../api'
import { useAuth } from '../../auth-context'
import { unwrap } from '../../lib/api-helpers'
import { TEMP_GROUP, TRIP_STATUS, fmtDate, fmtDateTime, fmtNumber } from '../../lib/labels'
import { MapView, type MapMarker, type MapRoute } from '../../lib/MapView'
import { useTripRoads } from '../../lib/roads'
import { loadPercent, type Trip } from '../../lib/trips'

type Run = components['schemas']['RunDetailOut']
type Unassigned = components['schemas']['UnassignedPart']

const COLORS = ['#1677ff', '#fa541c', '#52c41a', '#722ed1', '#eb2f96', '#13c2c2', '#faad14', '#2f54eb']
const RUN_STATUS: Record<Run['status'], { label: string; color: string }> = {
  QUEUED: { label: 'Đang chờ', color: 'default' },
  RUNNING: { label: 'Đang lập', color: 'processing' },
  SUCCEEDED: { label: 'Hoàn tất', color: 'green' },
  FAILED: { label: 'Lỗi', color: 'red' },
}
const SOURCE: Record<string, string> = {
  osrm: 'Đường bộ (OSRM)',
  cache: 'Đường bộ (OSRM, cache)',
  estimate: 'Ước lượng đường chim bay',
}
const fmtMoney = (v: number) => `${fmtNumber(Math.round(v))} đ`
const hhmm = (v: string | null | undefined) => (v ? fmtDateTime(v).slice(0, 5) : '')

export function PlanningRunPage() {
  const { runId = '' } = useParams()
  const navigate = useNavigate()
  const { hasRole } = useAuth()
  const canEdit = hasRole('manager')
  const run = useQuery({
    queryKey: ['planning-run', runId],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/planning/runs/{run_id}', { params: { path: { run_id: runId } } })),
    refetchInterval: (q) => (q.state.data && ['QUEUED', 'RUNNING'].includes(q.state.data.status) ? 2000 : false),
  })
  const tripIds = run.data?.trips.map((t) => t.id) ?? []
  const details = useQueries({
    queries: tripIds.map((id) => ({
      queryKey: ['trip', id],
      queryFn: async () => unwrap(await api.GET('/api/v1/trips/{trip_id}', { params: { path: { trip_id: id } } })),
    })),
  })
  const trips = details.map((d) => d.data).filter((t): t is Trip => Boolean(t))

  if (run.isLoading) return <Spin />
  if (!run.data) return <Result status="404" title="Không tìm thấy lần lập kế hoạch" />
  const r = run.data
  const s = r.summary
  const busy = r.status === 'QUEUED' || r.status === 'RUNNING'
  const color = (tripId: string) => COLORS[tripIds.indexOf(tripId) % COLORS.length]

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title={
          <Space>
            Kế hoạch tự động ngày {fmtDate(r.plan_date)}
            <Tag color={RUN_STATUS[r.status].color}>{RUN_STATUS[r.status].label}</Tag>
            {r.trigger === 'SCHEDULED' && <Tag>Theo lịch</Tag>}
          </Space>
        }
        extra={<Button onClick={() => navigate(`/plans?date=${r.plan_date}`)}>Về kế hoạch ngày</Button>}
      >
        {busy && <Alert type="info" showIcon title="Đang lập kế hoạch, kết quả sẽ tự cập nhật…" />}
        {r.status === 'FAILED' && <Alert type="error" showIcon title="Lập kế hoạch lỗi" description={r.error} />}
        {r.status === 'SUCCEEDED' && (
          <>
            <Row gutter={[16, 16]}>
              <Col xs={12} md={4}>
                <Statistic title="Chuyến" value={s.trips} />
              </Col>
              <Col xs={12} md={4}>
                <Statistic title="Phần đơn đã xếp" value={s.parts_assigned} suffix={`/ ${s.parts_total}`} />
              </Col>
              <Col xs={12} md={4}>
                <Statistic title="Khối lượng" value={fmtNumber(s.weight_kg)} suffix="kg" />
              </Col>
              <Col xs={12} md={4}>
                <Statistic title="Sử dụng tải" value={Math.round(s.utilization * 100)} suffix="%" />
              </Col>
              <Col xs={12} md={4}>
                <Statistic title="Quãng đường (tối ưu)" value={fmtNumber(s.distance_km)} suffix="km" />
              </Col>
              <Col xs={12} md={4}>
                <Statistic title="Chi phí (tối ưu)" value={fmtMoney(s.cost)} />
              </Col>
            </Row>
            <CostCompare run={r} />
            <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
              Khoảng cách: {SOURCE[r.distance_source ?? 'estimate']} · bộ giải {s.solve_seconds}s · lập lúc{' '}
              {fmtDateTime(r.finished_at)}
            </Typography.Paragraph>
            {r.warnings.length > 0 && (
              <Alert
                style={{ marginTop: 12 }}
                type="warning"
                showIcon
                title="Lưu ý"
                description={
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {r.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                }
              />
            )}
          </>
        )}
      </Card>

      {r.status === 'SUCCEEDED' && (
        <>
          <Card title="Bản đồ các chuyến">
            <RunMap trips={trips} color={color} />
          </Card>
          <Card
            title="Các chuyến"
            extra={canEdit && <Typography.Text type="secondary">Kéo thả điểm dừng để chuyển sang chuyến cùng kho / đổi thứ tự</Typography.Text>}
          >
            {trips.length === 0 ? <Empty description="Không có chuyến nào" /> : <TripBoard trips={trips} color={color} canEdit={canEdit} runId={r.id} />}
          </Card>
          <UnassignedTable rows={r.unassigned} planDate={r.plan_date} canEdit={canEdit} />
        </>
      )}
    </Space>
  )
}

function CostCompare({ run }: { run: Run }) {
  const { cost, distance_km } = run.current
  const diff = cost - run.summary.cost
  if (Math.abs(diff) < 1 && Math.abs(distance_km - run.summary.distance_km) < 0.05) return null
  return (
    <Alert
      style={{ marginTop: 12 }}
      type={diff > 0 ? 'warning' : 'success'}
      showIcon
      title={`Sau điều chỉnh: ${fmtNumber(distance_km)} km · ${fmtMoney(cost)} (${diff > 0 ? '+' : ''}${fmtMoney(diff)} so với phương án tối ưu)`}
    />
  )
}

function RunMap({ trips, color }: { trips: Trip[]; color: (id: string) => string }) {
  const markers: MapMarker[] = []
  const routes: MapRoute[] = []
  const warehouses = new Map<string, MapMarker>()
  for (const t of trips) {
    const depot: [number, number] = [Number(t.warehouse_longitude), Number(t.warehouse_latitude)]
    warehouses.set(t.warehouse_id, {
      id: t.warehouse_id,
      lat: depot[1],
      lng: depot[0],
      label: t.warehouse_code,
      color: '#262626',
      title: t.warehouse_name,
    })
    const coords: [number, number][] = [depot]
    for (const st of t.stops) {
      if (st.latitude == null || st.longitude == null) continue
      coords.push([Number(st.longitude), Number(st.latitude)])
      markers.push({
        id: st.id,
        lat: Number(st.latitude),
        lng: Number(st.longitude),
        label: `${t.code.slice(-2)}.${st.seq}`,
        color: color(t.id),
        title: `${t.code} · ${st.customer_name ?? st.name ?? ''}`,
      })
    }
    coords.push(depot)
    routes.push({ id: t.id, color: color(t.id), coords })
  }
  const roads = useTripRoads(routes)
  return <MapView markers={[...warehouses.values(), ...markers]} routes={roads} height={480} />
}

function TripBoard({
  trips,
  color,
  canEdit,
  runId,
}: {
  trips: Trip[]
  color: (id: string) => string
  canEdit: boolean
  runId: string
}) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [dragging, setDragging] = useState<{ tripId: string; stopId: string; warehouseId: string } | null>(null)
  const [over, setOver] = useState<string | null>(null)
  const move = useMutation({
    mutationFn: async (body: components['schemas']['MoveStopIn']) =>
      unwrap(await api.POST('/api/v1/planning/move-stop', { body })),
    onSuccess: async (res) => {
      res.warnings.forEach((w) => message.warning(w))
      await queryClient.invalidateQueries({ queryKey: ['trip'] })
      await queryClient.invalidateQueries({ queryKey: ['planning-run', runId] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const drop = (toTripId: string, position: number | null) => (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setOver(null)
    if (!dragging) return
    move.mutate({ from_trip_id: dragging.tripId, stop_id: dragging.stopId, to_trip_id: toTripId, position })
    setDragging(null)
  }

  return (
    <Spin spinning={move.isPending}>
      <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 8 }}>
        {trips.map((t) => (
          <div
            key={t.id}
            onDragOver={(e) => {
              // Chỉ chuyển giữa các chuyến cùng kho xuất (kho chọn theo kho gần nhất).
              if (!canEdit || !dragging || dragging.warehouseId !== t.warehouse_id) return
              e.preventDefault()
              setOver(t.id)
            }}
            onDragLeave={() => setOver((o) => (o === t.id ? null : o))}
            onDrop={drop(t.id, null)}
            style={{
              minWidth: 260,
              maxWidth: 300,
              flex: '0 0 auto',
              border: `2px solid ${over === t.id ? color(t.id) : '#f0f0f0'}`,
              boxShadow: `inset 0 4px 0 ${color(t.id)}`,
              borderRadius: 8,
              padding: 10,
              background: '#fafafa',
            }}
          >
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <a onClick={() => navigate(`/trips/${t.id}`)}>
                <b>{t.code}</b>
              </a>
              <Tag color={TRIP_STATUS[t.order_status].color}>{TRIP_STATUS[t.order_status].label}</Tag>
            </Space>
            <div style={{ fontSize: 12, color: '#666' }}>
              {t.vehicle_code} · lượt {t.trip_seq} · {t.warehouse_code}
              {t.planned_start && ` · ${hhmm(t.planned_start)}–${hhmm(t.planned_end)}`}
            </div>
            <Progress
              percent={loadPercent(t.total_weight_kg, t.capacity_kg)}
              size="small"
              format={() => `${fmtNumber(t.total_weight_kg)}/${fmtNumber(t.capacity_kg)} kg`}
            />
            {t.stops.map((st, index) => (
              <div
                key={st.id}
                draggable={canEdit}
                onDragStart={() => setDragging({ tripId: t.id, stopId: st.id, warehouseId: t.warehouse_id })}
                onDragEnd={() => setDragging(null)}
                onDragOver={(e) => canEdit && dragging?.warehouseId === t.warehouse_id && e.preventDefault()}
                onDrop={drop(t.id, index)}
                style={{
                  background: '#fff',
                  border: '1px solid #e8e8e8',
                  borderRadius: 6,
                  padding: '6px 8px',
                  marginTop: 6,
                  cursor: canEdit ? 'grab' : 'default',
                  opacity: dragging?.stopId === st.id ? 0.4 : 1,
                }}
              >
                <div>
                  <b>{st.seq}.</b> {st.customer_code ? `${st.customer_code} · ${st.customer_name}` : st.name}
                </div>
                <div style={{ fontSize: 12, color: '#888' }}>
                  {st.items
                    .filter((i) => i.status !== 'CANCELLED')
                    .map((i) => `${i.external_ref ?? i.description} (${fmtNumber(i.weight_kg)} kg)`)
                    .join(', ')}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </Spin>
  )
}

function UnassignedTable({ rows, planDate, canEdit }: { rows: Unassigned[]; planDate: string; canEdit: boolean }) {
  const navigate = useNavigate()
  return (
    <Card
      title={
        <Space>
          Phần đơn không xếp được
          <Tag color={rows.length ? 'red' : 'green'}>{rows.length}</Tag>
        </Space>
      }
      extra={
        canEdit &&
        rows.length > 0 && (
          <Button onClick={() => navigate(`/trips/new?date=${planDate}`)}>Lập lệnh thủ công</Button>
        )
      }
    >
      <Table<Unassigned>
        rowKey="order_part_id"
        dataSource={rows}
        pagination={false}
        size="small"
        locale={{ emptyText: 'Mọi phần đơn đều đã được xếp chuyến' }}
        columns={[
          { title: 'Số đơn', dataIndex: 'external_ref', width: 130 },
          { title: 'Khách hàng', render: (_, u) => `${u.customer_code} · ${u.customer_name}` },
          { title: 'Nhóm hàng', dataIndex: 'temp_group', width: 110, render: (v: Unassigned['temp_group']) => TEMP_GROUP[v] },
          { title: 'Khối lượng', dataIndex: 'weight_kg', width: 110, align: 'right', render: (v: number) => `${fmtNumber(v)} kg` },
          { title: 'Ngày yêu cầu', dataIndex: 'requested_date', width: 120, render: fmtDate },
          { title: 'Lý do', dataIndex: 'reason', render: (v: string) => <Typography.Text type="danger">{v}</Typography.Text> },
        ]}
      />
    </Card>
  )
}
