import { ArrowDownOutlined, ArrowUpOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'

import { api } from '../../api'
import { unwrap } from '../../lib/api-helpers'
import { CoordinateFields } from '../../lib/CoordinateFields'
import { TEMP_GROUP, VEHICLE_REQUIREMENT, fmtDate, fmtNumber } from '../../lib/labels'
import { MapView, type MapMarker } from '../../lib/MapView'
import { cargoCompatible, loadPercent, toISODate, vehicleMatches } from '../../lib/trips'

type S = components['schemas']
type Part = S['AvailablePartOut']
type TripIn = S['TripIn']

/** Thông tin phần đơn đủ để hiển thị và kiểm tra (từ danh sách chờ hoặc từ lệnh đang sửa). */
interface PartInfo {
  id: string
  label: string
  customer: string
  temp_group: S['TempGroup']
  weight: number
  requirement?: S['VehicleRequirement']
}

interface DraftStop {
  key: string
  delivery_point_id?: string
  title: string
  address: string
  lat: number
  lng: number
  partIds: string[]
  adhoc_items: { description: string; weight_kg: number }[]
}

interface HeaderForm {
  plan_date: Dayjs
  vehicle_id?: string
  warehouse_id?: string
  driver_id?: string
  assistant_id?: string
  note?: string
}

class TripSaveError extends Error {
  readonly details: string[]

  constructor(message: string, details: string[]) {
    super(message)
    this.details = details
  }
}

type Trip = S['TripOut']

/** Chuyển lệnh đang sửa thành danh sách điểm dừng nháp + thông tin phần đơn đã chọn. */
function draftFromTrip(t: Trip): { stops: DraftStop[]; known: Record<string, PartInfo> } {
  const known: Record<string, PartInfo> = {}
  const stops = t.stops.map((s) => {
    const parts = s.items.filter((i) => i.order_part_id && i.status !== 'CANCELLED')
    parts.forEach((i) => {
      known[i.order_part_id!] = {
        id: i.order_part_id!,
        label: i.external_ref ?? '',
        customer: s.customer_code ?? '',
        temp_group: i.temp_group!,
        weight: Number(i.weight_kg),
      }
    })
    return {
      key: s.id,
      delivery_point_id: s.delivery_point_id ?? undefined,
      title: s.customer_code ? `${s.customer_code} - ${s.customer_name}` : (s.name ?? 'Điểm tự do'),
      address: s.address ?? '',
      lat: Number(s.latitude),
      lng: Number(s.longitude),
      partIds: parts.map((i) => i.order_part_id!),
      adhoc_items: s.items
        .filter((i) => !i.order_part_id && i.status !== 'CANCELLED')
        .map((i) => ({ description: i.description ?? '', weight_kg: Number(i.weight_kg) })),
    }
  })
  return { stops, known }
}

export function TripEditor() {
  const { tripId } = useParams()
  const existing = useQuery({
    queryKey: ['trip', tripId],
    enabled: Boolean(tripId),
    queryFn: async () => unwrap(await api.GET('/api/v1/trips/{trip_id}', { params: { path: { trip_id: tripId! } } })),
  })
  if (tripId && !existing.data) return <Card loading />
  return <TripEditorForm key={tripId ?? 'new'} trip={existing.data} />
}

function TripEditorForm({ trip }: { trip?: Trip }) {
  const tripId = trip?.id
  const [search] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { message } = App.useApp()
  const [form] = Form.useForm<HeaderForm>()
  const [initial] = useState(() => (trip ? draftFromTrip(trip) : { stops: [], known: {} }))
  const [stops, setStops] = useState<DraftStop[]>(initial.stops)
  const known = initial.known
  const [errors, setErrors] = useState<string[]>([])
  const [adhocOpen, setAdhocOpen] = useState(false)
  const [filter, setFilter] = useState('')

  const planDate: Dayjs | undefined = Form.useWatch('plan_date', form)
  const vehicleId: string | undefined = Form.useWatch('vehicle_id', form)
  const warehouseId: string | undefined = Form.useWatch('warehouse_id', form)
  const planISO = planDate ? toISODate(planDate) : (search.get('date') ?? toISODate(dayjs()))

  const vehicles = useQuery({
    queryKey: ['vehicles', 'active'],
    queryFn: async () => unwrap(await api.GET('/api/v1/vehicles', { params: { query: { active: true, limit: 500 } } })),
  })
  const warehouses = useQuery({
    queryKey: ['warehouses', 'all'],
    queryFn: async () => unwrap(await api.GET('/api/v1/warehouses', { params: { query: { limit: 500 } } })),
  })
  const drivers = useQuery({
    queryKey: ['staff', 'driver'],
    queryFn: async () => unwrap(await api.GET('/api/v1/staff', { params: { query: { role: 'driver' } } })),
  })
  const available = useQuery({
    queryKey: ['available-parts', planISO],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/trips/available-parts', { params: { query: { plan_date: planISO } } })),
  })

  const vehicle = vehicles.data?.items.find((v) => v.id === vehicleId)
  const partInfo = useMemo(() => {
    const map: Record<string, PartInfo> = { ...known }
    available.data?.forEach((p) => {
      map[p.id] = {
        id: p.id,
        label: p.external_ref,
        customer: p.customer_code,
        temp_group: p.temp_group,
        weight: Number(p.weight_kg),
        requirement: p.required_vehicle_type,
      }
    })
    return map
  }, [available.data, known])

  const selectedIds = new Set(stops.flatMap((s) => s.partIds))
  const totalWeight =
    stops.reduce((sum, s) => sum + s.adhoc_items.reduce((a, i) => a + Number(i.weight_kg), 0), 0) +
    [...selectedIds].reduce((sum, id) => sum + (partInfo[id]?.weight ?? 0), 0)

  const problem = (p: { temp_group: S['TempGroup']; requirement?: S['VehicleRequirement'] }) => {
    if (!vehicle) return null
    if (!cargoCompatible(vehicle.cargo_class, p.temp_group)) return `Xe không chở hàng ${TEMP_GROUP[p.temp_group]}`
    if (p.requirement && !vehicleMatches(p.requirement, vehicle.vehicle_type))
      return `Khách yêu cầu ${VEHICLE_REQUIREMENT[p.requirement]}`
    return null
  }

  function addPart(p: Part) {
    setStops((prev) => {
      const idx = prev.findIndex((s) => s.delivery_point_id === p.delivery_point_id)
      if (idx >= 0) return prev.map((s, i) => (i === idx ? { ...s, partIds: [...s.partIds, p.id] } : s))
      return [
        ...prev,
        {
          key: p.delivery_point_id,
          delivery_point_id: p.delivery_point_id,
          title: `${p.customer_code} - ${p.customer_name}`,
          address: p.address,
          lat: Number(p.latitude),
          lng: Number(p.longitude),
          partIds: [p.id],
          adhoc_items: [],
        },
      ]
    })
  }

  const removePart = (stopKey: string, partId: string) =>
    setStops((prev) =>
      prev
        .map((s) => (s.key === stopKey ? { ...s, partIds: s.partIds.filter((id) => id !== partId) } : s))
        .filter((s) => s.partIds.length || s.adhoc_items.length),
    )
  const move = (index: number, delta: number) =>
    setStops((prev) => {
      const next = [...prev]
      const [item] = next.splice(index, 1)
      next.splice(index + delta, 0, item)
      return next
    })

  const save = useMutation({
    mutationFn: async (h: HeaderForm) => {
      const body: TripIn = {
        plan_date: toISODate(h.plan_date),
        vehicle_id: h.vehicle_id!,
        warehouse_id: h.warehouse_id!,
        driver_id: h.driver_id ?? null,
        assistant_id: h.assistant_id ?? null,
        note: h.note ?? null,
        stops: stops.map((s) =>
          s.delivery_point_id
            ? { delivery_point_id: s.delivery_point_id, order_part_ids: s.partIds, adhoc_items: s.adhoc_items }
            : {
                order_part_ids: [],
                name: s.title,
                address: s.address,
                latitude: s.lat.toFixed(6),
                longitude: s.lng.toFixed(6),
                adhoc_items: s.adhoc_items,
              },
        ),
      }
      const result = tripId
        ? await api.PUT('/api/v1/trips/{trip_id}', { params: { path: { trip_id: tripId } }, body })
        : await api.POST('/api/v1/trips', { body })
      if (!result.data) {
        const err = result.error as { error?: { message: string; details?: string[] } } | undefined
        throw new TripSaveError(err?.error?.message ?? 'Không lưu được lệnh', err?.error?.details ?? [])
      }
      return result.data
    },
    onSuccess: async (trip) => {
      await queryClient.invalidateQueries()
      message.success(`Đã lưu lệnh ${trip.code}`)
      navigate(`/trips/${trip.id}`, { state: { warnings: trip.warnings } })
    },
    onError: (e: Error) => setErrors(e instanceof TripSaveError && e.details.length ? e.details : [e.message]),
  })

  const warehouse = warehouses.data?.items.find((w) => w.id === warehouseId)
  const markers: MapMarker[] = [
    ...(warehouse
      ? [{ id: 'wh', lat: Number(warehouse.latitude), lng: Number(warehouse.longitude), label: warehouse.code, color: '#389e0d' }]
      : []),
    ...stops.map((s, i) => ({ id: s.key, lat: s.lat, lng: s.lng, label: String(i + 1), title: s.title })),
  ]
  const route: [number, number][] = warehouse
    ? [
        [Number(warehouse.longitude), Number(warehouse.latitude)],
        ...stops.map((s) => [s.lng, s.lat] as [number, number]),
        [Number(warehouse.longitude), Number(warehouse.latitude)],
      ]
    : []
  const pool = (available.data ?? []).filter(
    (p) =>
      !selectedIds.has(p.id) &&
      (!filter || `${p.external_ref} ${p.customer_code} ${p.customer_name}`.toLowerCase().includes(filter.toLowerCase())),
  )

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title={trip ? `Sửa lệnh ${trip.code}` : 'Lập lệnh giao'}
        extra={
          <Space>
            <Button onClick={() => navigate(-1)}>Hủy bỏ</Button>
            <Button type="primary" loading={save.isPending} disabled={!stops.length} onClick={() => form.submit()}>
              Lưu lệnh
            </Button>
          </Space>
        }
      >
        {trip?.order_status === 'APPROVED' && (
          <Alert type="warning" showIcon style={{ marginBottom: 16 }} title="Lệnh đã duyệt: sau khi sửa sẽ quay về nháp và cần duyệt lại." />
        )}
        {errors.length > 0 && (
          <Alert
            type="error"
            showIcon
            closable
            onClose={() => setErrors([])}
            style={{ marginBottom: 16 }}
            title="Lệnh giao chưa hợp lệ"
            description={<ul style={{ margin: 0, paddingLeft: 18 }}>{errors.map((e) => <li key={e}>{e}</li>)}</ul>}
          />
        )}
        <Form<HeaderForm>
          form={form}
          layout="vertical"
          onFinish={(v) => save.mutate(v)}
          initialValues={
            trip
              ? {
                  plan_date: dayjs(trip.plan_date),
                  vehicle_id: trip.vehicle_id,
                  warehouse_id: trip.warehouse_id,
                  driver_id: trip.driver?.id,
                  assistant_id: trip.assistant?.id,
                  note: trip.note ?? undefined,
                }
              : { plan_date: dayjs(search.get('date') ?? undefined) }
          }
        >
          <Row gutter={12}>
            <Col xs={24} md={4}>
              <Form.Item name="plan_date" label="Ngày giao" rules={[{ required: true }]}>
                <DatePicker format="DD/MM/YYYY" style={{ width: '100%' }} allowClear={false} />
              </Form.Item>
            </Col>
            <Col xs={24} md={6}>
              <Form.Item name="vehicle_id" label="Xe" rules={[{ required: true }]}>
                <Select
                  showSearch={{ optionFilterProp: 'label' }}
                  options={vehicles.data?.items.map((v) => ({
                    value: v.id,
                    label: `${v.code} - ${v.name} (${fmtNumber(v.capacity_kg)} kg)`,
                  }))}
                  onChange={() => form.setFieldValue('warehouse_id', undefined)}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={4}>
              <Form.Item name="warehouse_id" label="Kho xuất" rules={[{ required: true }]}>
                <Select
                  options={warehouses.data?.items
                    .filter((w) => !vehicle || vehicle.warehouse_ids.includes(w.id))
                    .map((w) => ({ value: w.id, label: `${w.code} - ${w.name}` }))}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={5}>
              <Form.Item name="driver_id" label="Lái xe">
                <Select allowClear options={drivers.data?.map((d) => ({ value: d.id, label: d.full_name }))} />
              </Form.Item>
            </Col>
            <Col xs={24} md={5}>
              <Form.Item
                name="assistant_id"
                label={vehicle?.requires_assistant ? 'Phụ xe (bắt buộc)' : 'Phụ xe'}
                rules={[{ required: Boolean(vehicle?.requires_assistant) }]}
              >
                <Select allowClear options={drivers.data?.map((d) => ({ value: d.id, label: d.full_name }))} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="note" label="Ghi chú">
            <Input />
          </Form.Item>
        </Form>
        {vehicle && (
          <Progress
            percent={loadPercent(totalWeight, vehicle.capacity_kg)}
            status={totalWeight > Number(vehicle.capacity_kg) ? 'exception' : 'normal'}
            format={() => `${fmtNumber(totalWeight)} / ${fmtNumber(vehicle.capacity_kg)} kg`}
          />
        )}
      </Card>

      <Row gutter={16}>
        <Col xs={24} xl={12}>
          <Card
            title={`Điểm dừng (${stops.length})`}
            extra={
              <Button icon={<PlusOutlined />} onClick={() => setAdhocOpen(true)}>
                Điểm tự do
              </Button>
            }
            style={{ marginBottom: 16 }}
          >
            {stops.length === 0 ? (
              <Empty description="Chọn phần đơn ở bảng bên dưới để thêm điểm dừng" />
            ) : (
              stops.map((s, index) => (
                <div key={s.key} style={{ display: 'flex', gap: 12, padding: '10px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <div style={{ flex: 1 }}>
                    <Typography.Text strong>{`${index + 1}. ${s.title}`}</Typography.Text>
                    <div>
                      <Typography.Text type="secondary">{s.address}</Typography.Text>
                    </div>
                          {s.partIds.map((id) => {
                            const p = partInfo[id]
                            return (
                              <Tag key={id} closable onClose={() => removePart(s.key, id)} color={problem(p ?? { temp_group: 'DRY' }) ? 'red' : undefined}>
                                {p?.label} · {p && TEMP_GROUP[p.temp_group]} · {fmtNumber(p?.weight)} kg
                              </Tag>
                            )
                          })}
                          {s.adhoc_items.map((i) => (
                            <Tag key={i.description}>
                              {i.description} · {fmtNumber(i.weight_kg)} kg
                            </Tag>
                          ))}
                  </div>
                  <Space align="start">
                    <Button size="small" icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => move(index, -1)} />
                    <Button size="small" icon={<ArrowDownOutlined />} disabled={index === stops.length - 1} onClick={() => move(index, 1)} />
                    <Button size="small" danger icon={<DeleteOutlined />} onClick={() => setStops((p) => p.filter((x) => x.key !== s.key))} />
                  </Space>
                </div>
              ))
            )}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title="Bản đồ" style={{ marginBottom: 16 }}>
            <MapView markers={markers} route={route} />
            <Typography.Text type="secondary">Đường nối thẳng theo thứ tự điểm dừng (định tuyến thực tế ở M4).</Typography.Text>
          </Card>
        </Col>
      </Row>

      <Card
        title={`Phần đơn chờ xếp lệnh (giao đến ${fmtDate(planISO)})`}
        extra={<Input.Search placeholder="Số đơn, khách hàng" allowClear onSearch={setFilter} style={{ width: 260 }} />}
      >
        <Table<Part>
          rowKey="id"
          size="small"
          loading={available.isLoading}
          dataSource={pool}
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          scroll={{ x: 900 }}
          columns={[
            { title: 'Số đơn', dataIndex: 'external_ref', width: 120 },
            { title: 'Khách hàng', render: (_, p) => `${p.customer_code} - ${p.customer_name}` },
            { title: 'Điểm', dataIndex: 'delivery_point_code', width: 70 },
            { title: 'Nhóm', dataIndex: 'temp_group', width: 90, render: (v: Part['temp_group']) => TEMP_GROUP[v] },
            { title: 'Kg', dataIndex: 'weight_kg', width: 80, align: 'right', render: fmtNumber },
            { title: 'Ngày YC', dataIndex: 'requested_date', width: 100, render: fmtDate },
            {
              title: '',
              width: 220,
              render: (_, p) => {
                const issue = problem({ temp_group: p.temp_group, requirement: p.required_vehicle_type })
                return (
                  <Space>
                    {p.status === 'FAILED' && <Tag color="red">Giao lại</Tag>}
                    {issue && <Tag color="orange">{issue}</Tag>}
                    <Button size="small" disabled={Boolean(issue)} onClick={() => addPart(p)}>
                      Thêm
                    </Button>
                  </Space>
                )
              },
            },
          ]}
        />
      </Card>

      <AdhocStopModal
        open={adhocOpen}
        onClose={() => setAdhocOpen(false)}
        onAdd={(stop) => setStops((prev) => [...prev, stop])}
      />
    </Space>
  )
}

interface AdhocForm {
  name: string
  address: string
  latitude: string
  longitude: string
  description: string
  weight_kg?: number
}

function AdhocStopModal({ open, onClose, onAdd }: { open: boolean; onClose: () => void; onAdd: (s: DraftStop) => void }) {
  const [form] = Form.useForm<AdhocForm>()
  return (
    <Modal
      open={open}
      title="Thêm điểm dừng tự do (không theo đơn)"
      okText="Thêm"
      cancelText="Hủy"
      onCancel={onClose}
      onOk={() => form.submit()}
      destroyOnHidden
    >
      <Form<AdhocForm>
        form={form}
        layout="vertical"
        onFinish={(v) => {
          onAdd({
            key: `adhoc-${Date.now()}`,
            title: v.name,
            address: v.address,
            lat: Number(v.latitude),
            lng: Number(v.longitude),
            partIds: [],
            adhoc_items: [{ description: v.description, weight_kg: v.weight_kg ?? 0 }],
          })
          onClose()
        }}
      >
        <Form.Item name="name" label="Tên điểm" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="address" label="Địa chỉ" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <CoordinateFields />
        <Form.Item name="description" label="Hàng giao / công việc" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="weight_kg" label="Khối lượng (kg)">
          <InputNumber min={0} style={{ width: '100%' }} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
