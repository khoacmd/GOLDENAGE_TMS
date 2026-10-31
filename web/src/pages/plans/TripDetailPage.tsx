import { PrinterOutlined } from '@ant-design/icons'
import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Image,
  Input,
  Modal,
  Popconfirm,
  Row,
  Space,
  Table,
  Tag,
  Timeline,
} from 'antd'
import { useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router'

import { api } from '../../api'
import { useAuth } from '../../auth-context'
import { unwrap } from '../../lib/api-helpers'
import {
  DELIVERY_STATUS,
  ITEM_STATUS,
  TEMP_GROUP,
  TRIP_ACTION,
  TRIP_STATUS,
  fmtDate,
  fmtDateTime,
  fmtNumber,
} from '../../lib/labels'
import { MapView, type MapMarker } from '../../lib/MapView'
import { useTripRoads } from '../../lib/roads'
import { TripCostCard } from './TripCostCard'

type Item = components['schemas']['TripItemOut']
type ItemStatus = components['schemas']['ItemStatus']

export function TripDetailPage() {
  const { tripId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { hasRole } = useAuth()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [reasonFor, setReasonFor] = useState<{ item: Item; status: ItemStatus } | 'cancel' | null>(null)
  const warnings = (location.state as { warnings?: string[] } | null)?.warnings ?? []
  const path = { params: { path: { trip_id: tripId! } } }

  const query = useQuery({
    queryKey: ['trip', tripId],
    queryFn: async () => unwrap(await api.GET('/api/v1/trips/{trip_id}', path)),
  })
  const history = useQuery({
    queryKey: ['trip', tripId, 'history'],
    queryFn: async () => unwrap(await api.GET('/api/v1/trips/{trip_id}/history', path)),
  })
  const confirmations = useQuery({
    queryKey: ['trip', tripId, 'confirmations'],
    queryFn: async () => unwrap(await api.GET('/api/v1/trips/{trip_id}/confirmations', path)),
  })
  const refresh = () => queryClient.invalidateQueries()
  const action = useMutation({
    mutationFn: async (fn: () => Promise<unknown>) => fn(),
    onSuccess: async () => {
      message.success('Đã cập nhật')
      setReasonFor(null)
      await refresh()
    },
    onError: (e: Error) => message.error(e.message),
  })
  const run = (fn: () => Promise<unknown>) => action.mutate(fn)

  const trip = query.data
  if (!trip) return <Card loading />
  const isManager = hasRole('manager')
  const s = trip.order_status
  const editable = isManager && (s === 'DRAFT' || s === 'APPROVED' || s === 'PREPARED')
  const canUpdateItems = isManager && s === 'DISPATCHED'

  const updateItem = (item: Item, status: ItemStatus, reason?: string) =>
    run(async () =>
      unwrap(
        await api.PATCH('/api/v1/trips/{trip_id}/items/{item_id}', {
          params: { path: { trip_id: trip.id, item_id: item.id } },
          body: { status, reason: reason ?? null },
        }),
      ),
    )

  const markers = [
    { id: 'wh', lat: Number(trip.warehouse_latitude), lng: Number(trip.warehouse_longitude), label: trip.warehouse_code, color: '#389e0d' },
    ...trip.stops.map((st) => ({
      id: st.id,
      lat: Number(st.latitude),
      lng: Number(st.longitude),
      label: String(st.seq),
      title: st.customer_name ?? st.name ?? '',
      color: st.items.every((i) => i.status === 'SUCCESS') ? '#389e0d' : st.items.some((i) => i.status === 'FAILED') ? '#cf1322' : '#1677ff',
    })),
  ]
  const wh: [number, number] = [Number(trip.warehouse_longitude), Number(trip.warehouse_latitude)]
  const route: [number, number][] = [wh, ...trip.stops.map((st) => [Number(st.longitude), Number(st.latitude)] as [number, number]), wh]

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title={
          <Space>
            Lệnh {trip.code}
            <Tag color={TRIP_STATUS[s].color}>{TRIP_STATUS[s].label}</Tag>
            <Tag color={DELIVERY_STATUS[trip.delivery_status].color}>{DELIVERY_STATUS[trip.delivery_status].label}</Tag>
          </Space>
        }
        extra={
          <Space wrap>
            <Button icon={<PrinterOutlined />} onClick={() => window.open(`/print/trips/${trip.id}/picking`, '_blank')}>
              Phiếu soạn hàng
            </Button>
            <Button icon={<PrinterOutlined />} onClick={() => window.open(`/print/trips/${trip.id}/delivery`, '_blank')}>
              Phiếu giao hàng
            </Button>
            {editable && <Button onClick={() => navigate(`/trips/${trip.id}/edit`)}>Sửa</Button>}
            {editable && (
              <Button danger onClick={() => setReasonFor('cancel')}>
                Hủy lệnh
              </Button>
            )}
            {isManager && s === 'DRAFT' && (
              <Button type="primary" loading={action.isPending} onClick={() => run(async () => unwrap(await api.POST('/api/v1/trips/{trip_id}/approve', path)))}>
                Duyệt lệnh
              </Button>
            )}
            {hasRole('warehouse_keeper') && s === 'APPROVED' && (
              <Popconfirm title="Xác nhận đã soạn đủ hàng theo phiếu soạn hàng?" onConfirm={() => run(async () => unwrap(await api.POST('/api/v1/trips/{trip_id}/prepare', path)))}>
                <Button type="primary">Xác nhận soạn hàng</Button>
              </Popconfirm>
            )}
            {hasRole('warehouse_keeper') && s === 'PREPARED' && (
              <Popconfirm title="Xác nhận đã giao đủ hàng lên xe (xuất kho)?" onConfirm={() => run(async () => unwrap(await api.POST('/api/v1/trips/{trip_id}/pick', path)))}>
                <Button type="primary">Xác nhận xuất kho</Button>
              </Popconfirm>
            )}
            {isManager && s === 'PICKED' && (
              <Button type="primary" onClick={() => run(async () => unwrap(await api.POST('/api/v1/trips/{trip_id}/dispatch', path)))}>
                Xe xuất phát
              </Button>
            )}
            {isManager && s === 'DISPATCHED' && trip.delivery_status === 'FINISHED' && (
              <Popconfirm title="Xác nhận kết thúc chuyến?" onConfirm={() => run(async () => unwrap(await api.POST('/api/v1/trips/{trip_id}/close', path)))}>
                <Button type="primary">Kết thúc chuyến</Button>
              </Popconfirm>
            )}
          </Space>
        }
      >
        {warnings.length > 0 && (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            title="Lưu ý"
            description={<ul style={{ margin: 0, paddingLeft: 18 }}>{warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
          />
        )}
        {trip.cancel_reason && <Alert type="error" showIcon style={{ marginBottom: 16 }} title={`Đã hủy: ${trip.cancel_reason}`} />}
        <Descriptions size="small" column={{ xs: 1, md: 3 }} bordered>
          <Descriptions.Item label="Ngày giao">{fmtDate(trip.plan_date)}</Descriptions.Item>
          <Descriptions.Item label="Xe">
            {trip.vehicle_code} - {trip.vehicle_name} (lượt {trip.trip_seq})
          </Descriptions.Item>
          <Descriptions.Item label="Kho xuất">
            {trip.warehouse_code} - {trip.warehouse_name}
          </Descriptions.Item>
          <Descriptions.Item label="Lái xe">{trip.driver?.full_name ?? <Tag color="orange">Chưa phân công</Tag>}</Descriptions.Item>
          <Descriptions.Item label="Phụ xe">{trip.assistant?.full_name}</Descriptions.Item>
          <Descriptions.Item label="Khối lượng">
            {fmtNumber(trip.total_weight_kg)} / {fmtNumber(trip.capacity_kg)} kg
          </Descriptions.Item>
          <Descriptions.Item label="Giá trị hàng">{fmtNumber(trip.total_value)} đ</Descriptions.Item>
          <Descriptions.Item label="Kết quả giao">
            {Object.entries(trip.item_counts).map(([k, v]) => (
              <Tag key={k} color={ITEM_STATUS[k as ItemStatus].color}>
                {ITEM_STATUS[k as ItemStatus].label}: {v}
              </Tag>
            ))}
          </Descriptions.Item>
          <Descriptions.Item label="Ghi chú">{trip.note}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Row gutter={16}>
        <Col xs={24} xl={14}>
          <Card title="Điểm dừng" style={{ marginBottom: 16 }}>
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={trip.stops}
              expandable={{ defaultExpandAllRows: true, showExpandColumn: false, expandedRowKeys: trip.stops.map((st) => st.id) }}
              columns={[
                { title: '#', dataIndex: 'seq', width: 40 },
                {
                  title: 'Điểm giao',
                  render: (_, st) => (
                    <>
                      <b>{st.customer_code ? `${st.customer_code} - ${st.customer_name}` : st.name}</b>
                      <div>{st.address}</div>
                      {st.items.map((i) => (
                        <div key={i.id} style={{ marginTop: 4 }}>
                          <Tag color={ITEM_STATUS[i.status].color}>{ITEM_STATUS[i.status].label}</Tag>
                          {i.external_ref ? `${i.external_ref} · ${TEMP_GROUP[i.temp_group!]}` : i.description} · {fmtNumber(i.weight_kg)} kg
                          {i.reason && <i> - {i.reason}</i>}
                          {canUpdateItems && i.status !== 'CANCELLED' && (
                            <Space size={4} style={{ marginLeft: 8 }}>
                              {i.status !== 'SUCCESS' && (
                                <Button size="small" onClick={() => updateItem(i, 'SUCCESS')}>
                                  Thành công
                                </Button>
                              )}
                              {i.status !== 'FAILED' && (
                                <Button size="small" danger onClick={() => setReasonFor({ item: i, status: 'FAILED' })}>
                                  Thất bại
                                </Button>
                              )}
                              {i.status === 'PENDING' && (
                                <Button size="small" onClick={() => setReasonFor({ item: i, status: 'CANCELLED' })}>
                                  Hủy
                                </Button>
                              )}
                            </Space>
                          )}
                        </div>
                      ))}
                    </>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title="Bản đồ" style={{ marginBottom: 16 }}>
            <TripMap tripId={trip.id} markers={markers} route={route} />
          </Card>
          {(trip.order_status === 'DISPATCHED' || trip.order_status === 'CLOSED') && <TripCostCard trip={trip} />}
          {(confirmations.data?.length ?? 0) > 0 && (
            <Card title="Xác nhận từ nhân viên giao hàng" style={{ marginBottom: 16 }}>
              {confirmations.data?.map((c) => {
                  const item = trip.stops.flatMap((st) => st.items).find((i) => i.id === c.item_id)
                  return (
                    <div key={c.id} style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                      <Space orientation="vertical" size={2} style={{ width: '100%' }}>
                        <Space wrap>
                          <Tag color={c.accepted ? ITEM_STATUS[c.status].color : 'orange'}>
                            {c.accepted ? ITEM_STATUS[c.status].label : 'Bị từ chối'}
                          </Tag>
                          <span>{item?.external_ref ?? item?.description}</span>
                          <span style={{ color: '#888' }}>{fmtDateTime(c.device_time)}</span>
                        </Space>
                        <span style={{ fontSize: 12, color: '#666' }}>
                          {c.distance_m !== null ? `Cách điểm giao ${fmtNumber(c.distance_m)} m` : 'Không có GPS'}
                          {c.accuracy_m !== null && ` (sai số ${fmtNumber(c.accuracy_m)} m)`}
                          {c.is_mock_location && ' · vị trí giả lập'}
                          {c.reason && ` · ${c.reason}`}
                        </span>
                        {c.violations.map((v) => (
                          <span key={v} style={{ fontSize: 12, color: '#cf1322' }}>
                            {v}
                          </span>
                        ))}
                        {c.photos.length > 0 && (
                          <Image.PreviewGroup>
                            <Space>
                              {c.photos.map((p) => (
                                <Image key={p.key} src={p.url} width={64} height={64} style={{ objectFit: 'cover' }} />
                              ))}
                            </Space>
                          </Image.PreviewGroup>
                        )}
                      </Space>
                    </div>
                  )
                })}
            </Card>
          )}
          <Card title="Lịch sử">
            <Timeline
              items={history.data?.map((h) => ({
                content: (
                  <>
                    {TRIP_ACTION[h.action] ?? h.action}
                    {h.action === 'item_updated' && ` → ${ITEM_STATUS[h.data.status as ItemStatus]?.label}`}
                    {typeof h.data.reason === 'string' && h.data.reason && ` (${h.data.reason})`}
                    <div style={{ color: '#888', fontSize: 12 }}>{fmtDateTime(h.created_at)}</div>
                  </>
                ),
              }))}
            />
          </Card>
        </Col>
      </Row>

      <Modal
        open={reasonFor !== null}
        title={reasonFor === 'cancel' ? 'Hủy lệnh giao' : reasonFor?.status === 'FAILED' ? 'Giao không thành công' : 'Hủy mục hàng'}
        okText="Xác nhận"
        cancelText="Đóng"
        confirmLoading={action.isPending}
        onCancel={() => setReasonFor(null)}
        destroyOnHidden
        okButtonProps={{ htmlType: 'submit', form: 'reason-form' }}
      >
        <Form<{ reason: string }>
          id="reason-form"
          layout="vertical"
          onFinish={({ reason }) => {
            if (reasonFor === 'cancel')
              run(async () => unwrap(await api.POST('/api/v1/trips/{trip_id}/cancel', { ...path, body: { reason } })))
            else if (reasonFor) updateItem(reasonFor.item, reasonFor.status, reason)
          }}
        >
          <Form.Item name="reason" label="Lý do" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}

function TripMap({ tripId, markers, route }: { tripId: string; markers: MapMarker[]; route: [number, number][] }) {
  const routes = useTripRoads([{ id: tripId, color: '#1677ff', coords: route }])
  return <MapView markers={markers} routes={routes} height={360} />
}
