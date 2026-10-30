import { DownloadOutlined } from '@ant-design/icons'
import type { components } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { Alert, App, Button, Card, Col, DatePicker, Row, Select, Space, Statistic, Table, Tabs, type TableColumnType } from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useState } from 'react'

import { api } from '../api'
import { unwrap } from '../lib/api-helpers'
import { fmtDate, fmtNumber } from '../lib/labels'
import { toISODate } from '../lib/trips'

type S = components['schemas']
type Totals = S['Totals']

const pct = (v: number | null | undefined) => (v == null ? '–' : `${(v * 100).toFixed(1)}%`)
const money = (v: number | null | undefined) => (v == null ? '–' : `${fmtNumber(Math.round(v))} đ`)

/** Cột số liệu dùng chung cho bảng theo xe / theo ngày. */
function totalColumns<T extends Totals>() {
  return [
    { title: 'Chuyến', dataIndex: 'trips', align: 'right' as const, width: 80 },
    { title: 'Thành công', dataIndex: 'items_success', align: 'right' as const, width: 100 },
    { title: 'Thất bại', dataIndex: 'items_failed', align: 'right' as const, width: 90 },
    { title: 'Tỷ lệ TC', dataIndex: 'success_rate', align: 'right' as const, width: 90, render: pct },
    { title: 'Giao lại', dataIndex: 'redeliveries', align: 'right' as const, width: 80 },
    { title: 'Khối lượng', dataIndex: 'delivered_kg', align: 'right' as const, render: (v: number) => `${fmtNumber(v)} kg` },
    { title: 'Km', dataIndex: 'distance_km', align: 'right' as const, render: (v: number) => fmtNumber(v) },
    { title: '% tải', dataIndex: 'load_utilization', align: 'right' as const, width: 80, render: pct },
    { title: 'Chi phí', dataIndex: 'cost', align: 'right' as const, render: money },
    { title: 'Chi phí/đơn', dataIndex: 'cost_per_order', align: 'right' as const, render: money },
    { title: 'Chi phí/kg', dataIndex: 'cost_per_kg', align: 'right' as const, render: money },
  ].map((c) => c as TableColumnType<T>)
}

export function ReportsPage() {
  const { message } = App.useApp()
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().startOf('month'), dayjs()])
  const [vehicleId, setVehicleId] = useState<string>()
  const [warehouseId, setWarehouseId] = useState<string>()
  const [exporting, setExporting] = useState(false)
  const query = {
    date_from: toISODate(range[0]),
    date_to: toISODate(range[1]),
    vehicle_id: vehicleId,
    warehouse_id: warehouseId,
  }
  const report = useQuery({
    queryKey: ['report', query],
    queryFn: async () => unwrap(await api.GET('/api/v1/reports/summary', { params: { query } })),
  })
  const vehicles = useQuery({
    queryKey: ['vehicles', 'all'],
    queryFn: async () => unwrap(await api.GET('/api/v1/vehicles', { params: { query: { limit: 500 } } })),
  })
  const warehouses = useQuery({
    queryKey: ['warehouses', 'all'],
    queryFn: async () => unwrap(await api.GET('/api/v1/warehouses', { params: { query: { limit: 500 } } })),
  })

  async function exportExcel() {
    setExporting(true)
    try {
      const res = await api.GET('/api/v1/reports/export', { params: { query }, parseAs: 'blob' })
      if (!res.data) throw new Error('Không xuất được báo cáo')
      const url = URL.createObjectURL(res.data as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `bao-cao-giao-hang_${query.date_from}_${query.date_to}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setExporting(false)
    }
  }

  const t = report.data?.totals
  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title="Báo cáo giao hàng & chi phí"
        extra={
          <Space wrap>
            <DatePicker.RangePicker
              allowClear={false}
              format="DD/MM/YYYY"
              value={range}
              onChange={(v) => v?.[0] && v[1] && setRange([v[0], v[1]])}
            />
            <Select
              allowClear
              placeholder="Tất cả xe"
              style={{ width: 160 }}
              value={vehicleId}
              onChange={setVehicleId}
              options={vehicles.data?.items.map((v) => ({ value: v.id, label: `${v.code} - ${v.name}` }))}
            />
            <Select
              allowClear
              placeholder="Tất cả kho"
              style={{ width: 160 }}
              value={warehouseId}
              onChange={setWarehouseId}
              options={warehouses.data?.items.map((w) => ({ value: w.id, label: w.name }))}
            />
            <Button icon={<DownloadOutlined />} loading={exporting} onClick={() => void exportExcel()}>
              Xuất Excel
            </Button>
          </Space>
        }
        loading={report.isLoading}
      >
        {report.error && <Alert type="error" showIcon title={report.error.message} />}
        {t && (
          <>
            <Row gutter={[16, 16]}>
              <Col xs={12} md={6} xl={3}>
                <Statistic
                  title={t.trips_closed < t.trips ? `Chuyến (${t.trips_closed} đã kết thúc)` : 'Chuyến'}
                  value={t.trips}
                />
              </Col>
              <Col xs={12} md={6} xl={3}>
                <Statistic title="Tỷ lệ giao thành công" value={pct(t.success_rate)} />
              </Col>
              <Col xs={12} md={6} xl={3}>
                <Statistic title="Lượt giao lại" value={t.redeliveries} />
              </Col>
              <Col xs={12} md={6} xl={3}>
                <Statistic title="Quãng đường" value={fmtNumber(t.distance_km)} suffix="km" />
              </Col>
              <Col xs={12} md={6} xl={3}>
                <Statistic title="% tải trọng sử dụng" value={pct(t.load_utilization)} />
              </Col>
              <Col xs={12} md={6} xl={3}>
                <Statistic title="Tổng chi phí" value={money(t.cost)} />
              </Col>
              <Col xs={12} md={6} xl={3}>
                <Statistic title="Chi phí / đơn" value={money(t.cost_per_order)} />
              </Col>
              <Col xs={12} md={6} xl={3}>
                <Statistic title="Chi phí / kg" value={money(t.cost_per_kg)} />
              </Col>
            </Row>
            {t.trips_without_cost > 0 && (
              <Alert
                style={{ marginTop: 16 }}
                type="info"
                showIcon
                title={`${t.trips_without_cost} chuyến chưa ghi nhận chi phí (không tính vào tổng chi phí); km tạm tính theo kế hoạch / ước lượng tuyến. Chi phí tự ghi nhận khi kết thúc chuyến.`}
              />
            )}
          </>
        )}
      </Card>
      {report.data && (
        <Card>
          <Tabs
            items={[
              {
                key: 'vehicle',
                label: 'Theo xe',
                children: (
                  <Table<S['VehicleRow']>
                    rowKey="vehicle_id"
                    size="small"
                    pagination={false}
                    scroll={{ x: 1100 }}
                    dataSource={report.data.by_vehicle}
                    columns={[
                      { title: 'Xe', render: (_, r) => `${r.vehicle_code} - ${r.vehicle_name}`, width: 200 },
                      ...totalColumns<S['VehicleRow']>(),
                    ]}
                  />
                ),
              },
              {
                key: 'day',
                label: 'Theo ngày',
                children: (
                  <Table<S['DayRow']>
                    rowKey="plan_date"
                    size="small"
                    pagination={false}
                    scroll={{ x: 1100 }}
                    dataSource={report.data.by_day}
                    columns={[
                      { title: 'Ngày', dataIndex: 'plan_date', render: fmtDate, width: 110 },
                      ...totalColumns<S['DayRow']>(),
                    ]}
                  />
                ),
              },
              {
                key: 'customer',
                label: 'Theo khách hàng',
                children: (
                  <Table<S['CustomerRow']>
                    rowKey="customer_id"
                    size="small"
                    pagination={{ pageSize: 20 }}
                    dataSource={report.data.by_customer}
                    columns={[
                      { title: 'Khách hàng', render: (_, r) => `${r.customer_code} - ${r.customer_name}` },
                      { title: 'Số đơn', dataIndex: 'orders', align: 'right' },
                      { title: 'Thành công', dataIndex: 'items_success', align: 'right' },
                      { title: 'Thất bại', dataIndex: 'items_failed', align: 'right' },
                      { title: 'Khối lượng', dataIndex: 'delivered_kg', align: 'right', render: (v: number) => `${fmtNumber(v)} kg` },
                      { title: 'Chi phí phân bổ', dataIndex: 'cost', align: 'right', render: money },
                      { title: 'Chi phí/kg', dataIndex: 'cost_per_kg', align: 'right', render: money },
                    ]}
                  />
                ),
              },
              {
                key: 'reasons',
                label: 'Lý do thất bại',
                children: (
                  <Table<S['ReasonRow']>
                    rowKey="reason"
                    size="small"
                    pagination={false}
                    dataSource={report.data.failure_reasons}
                    locale={{ emptyText: 'Không có lượt giao thất bại' }}
                    columns={[
                      { title: 'Lý do', dataIndex: 'reason' },
                      { title: 'Số lượt', dataIndex: 'count', align: 'right', width: 120 },
                    ]}
                  />
                ),
              },
            ]}
          />
        </Card>
      )}
    </Space>
  )
}
