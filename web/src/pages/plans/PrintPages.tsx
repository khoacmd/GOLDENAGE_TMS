import { useQuery } from '@tanstack/react-query'
import { Button, Spin } from 'antd'
import { useState, type ReactNode } from 'react'
import { useParams } from 'react-router'

import { api } from '../../api'
import { unwrap } from '../../lib/api-helpers'
import { TEMP_GROUP, fmtDate, fmtDateTime, fmtNumber } from '../../lib/labels'

const page = { maxWidth: 820, margin: '0 auto', padding: 24, background: '#fff', color: '#000', fontSize: 13 }
const table = { width: '100%', borderCollapse: 'collapse' as const, marginTop: 12 }
const cell = { border: '1px solid #000', padding: '4px 6px' }

function PrintShell({ title, children }: { title: string; children: ReactNode }) {
  const [printedAt] = useState(() => new Date().toISOString())
  return (
    <div style={page}>
      <style>{'@media print { .no-print { display: none } body { background: #fff } }'}</style>
      <div className="no-print" style={{ textAlign: 'right', marginBottom: 12 }}>
        <Button type="primary" onClick={() => window.print()}>
          In / Lưu PDF
        </Button>
      </div>
      <h2 style={{ textAlign: 'center', margin: 0 }}>{title}</h2>
      {children}
      <table style={{ width: '100%', marginTop: 40, textAlign: 'center' }}>
        <tbody>
          <tr>
            <td>Người lập</td>
            <td>Thủ kho</td>
            <td>Lái xe</td>
          </tr>
        </tbody>
      </table>
      <p style={{ marginTop: 60, fontSize: 11, color: '#666' }}>In lúc {fmtDateTime(printedAt)}</p>
    </div>
  )
}

export function PickingListPrint() {
  const { tripId } = useParams()
  const query = useQuery({
    queryKey: ['picking', tripId],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/trips/{trip_id}/picking-list', { params: { path: { trip_id: tripId! } } })),
  })
  const data = query.data
  if (!data) return <Spin />
  const t = data.trip
  return (
    <PrintShell title="PHIẾU SOẠN HÀNG">
      <p style={{ textAlign: 'center' }}>
        Lệnh {t.code} · Ngày giao {fmtDate(t.plan_date)} · Kho {t.warehouse_code} · Xe {t.vehicle_code} (lượt {t.trip_seq}) ·
        Lái xe {t.driver?.full_name ?? '-'}
      </p>
      <table style={table}>
        <thead>
          <tr>
            {['#', 'Mã hàng', 'Tên hàng', 'Nhóm', 'Số lượng', 'ĐVT', 'Kg', 'Thực xuất'].map((h) => (
              <th key={h} style={cell}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.lines.map((l, i) => (
            <tr key={l.product_code}>
              <td style={cell}>{i + 1}</td>
              <td style={cell}>{l.product_code}</td>
              <td style={cell}>{l.product_name}</td>
              <td style={cell}>{TEMP_GROUP[l.temp_group]}</td>
              <td style={{ ...cell, textAlign: 'right' }}>{fmtNumber(l.qty)}</td>
              <td style={cell}>{l.uom}</td>
              <td style={{ ...cell, textAlign: 'right' }}>{fmtNumber(l.weight_kg)}</td>
              <td style={{ ...cell, width: 80 }} />
            </tr>
          ))}
        </tbody>
      </table>
      {data.adhoc_items.length > 0 && <p>Hàng khác: {data.adhoc_items.join('; ')}</p>}
      <p>
        Tổng khối lượng: <b>{fmtNumber(t.total_weight_kg)} kg</b>
      </p>
    </PrintShell>
  )
}

export function DeliveryNotesPrint() {
  const { tripId } = useParams()
  const query = useQuery({
    queryKey: ['trip', tripId],
    queryFn: async () => unwrap(await api.GET('/api/v1/trips/{trip_id}', { params: { path: { trip_id: tripId! } } })),
  })
  const t = query.data
  if (!t) return <Spin />
  return (
    <PrintShell title="PHIẾU GIAO HÀNG">
      <p style={{ textAlign: 'center' }}>
        Lệnh {t.code} · Ngày {fmtDate(t.plan_date)} · Xe {t.vehicle_code} · Lái xe {t.driver?.full_name ?? '-'}
        {t.assistant && ` · Phụ xe ${t.assistant.full_name}`}
      </p>
      <table style={table}>
        <thead>
          <tr>
            {['#', 'Khách hàng / địa chỉ', 'Đơn hàng', 'Kg', 'Giá trị (đ)', 'Ký nhận'].map((h) => (
              <th key={h} style={cell}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {t.stops.map((st) => (
            <tr key={st.id}>
              <td style={cell}>{st.seq}</td>
              <td style={cell}>
                <b>{st.customer_code ? `${st.customer_code} - ${st.customer_name}` : st.name}</b>
                <div>{st.address}</div>
              </td>
              <td style={cell}>
                {st.items
                  .filter((i) => i.status !== 'CANCELLED')
                  .map((i) => (
                    <div key={i.id}>{i.external_ref ? `${i.external_ref} (${TEMP_GROUP[i.temp_group!]})` : i.description}</div>
                  ))}
              </td>
              <td style={{ ...cell, textAlign: 'right' }}>
                {fmtNumber(st.items.filter((i) => i.status !== 'CANCELLED').reduce((s, i) => s + Number(i.weight_kg), 0))}
              </td>
              <td style={{ ...cell, textAlign: 'right' }}>
                {fmtNumber(st.items.filter((i) => i.status !== 'CANCELLED').reduce((s, i) => s + Number(i.value), 0))}
              </td>
              <td style={{ ...cell, width: 110, height: 48 }} />
            </tr>
          ))}
        </tbody>
      </table>
    </PrintShell>
  )
}
