import type { components } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { Button, Spin } from 'antd'
import { useMemo, useState, type ReactNode } from 'react'
import { useParams } from 'react-router'

import { api } from '../../api'
import { unwrap } from '../../lib/api-helpers'
import { TEMP_GROUP, fmtDate, fmtDateTime, fmtNumber } from '../../lib/labels'
import { PagedDocuments, type PrintDoc } from '../../lib/PagedDocument'
import { printCell as cell } from '../../lib/printStyles'

type Profile = components['schemas']['PrintProfileOut']
type Note = components['schemas']['DeliveryNoteOut']
type Notes = components['schemas']['DeliveryNotesOut']
type Picking = components['schemas']['PickingListOut']

const right = { ...cell, textAlign: 'right' as const }
const th = { ...cell, fontWeight: 600, textAlign: 'center' as const }
// Mã hàng dài (18 chữ số), nhóm hàng: không xuống dòng.
const code = { ...cell, fontSize: 11, whiteSpace: 'nowrap' as const, overflow: 'hidden' }

/** 100 Hộp với 48 Hộp = 1 Thùng → "2 Thùng + 4 Hộp"; SKU không nhỏ hơn ĐVT → null. */
function packText(l: {
  whole_uom: number | null
  rest_sku: number | string | null
  uom: string
  sku_uom: string
}) {
  if (l.whole_uom === null) return null
  const parts = []
  if (l.whole_uom > 0) parts.push(`${fmtNumber(l.whole_uom)} ${l.uom}`)
  if (Number(l.rest_sku) > 0) parts.push(`${fmtNumber(l.rest_sku)} ${l.sku_uom}`)
  return parts.join(' + ')
}

function usePrintProfile() {
  return useQuery({
    queryKey: ['print-profile'],
    queryFn: async () => unwrap(await api.GET('/api/v1/company/print-profile')),
  })
}

/** Đầu phiếu: logo + nội dung đầu trang theo mẫu của công ty (dòng đầu in đậm), bên phải số phiếu. */
export function PrintHeader({ profile, text, aside }: { profile: Profile; text?: string | null; aside?: ReactNode }) {
  const [first, ...rest] = (text || profile.company_name).split('\n')
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '4mm', minHeight: '18mm' }}>
      {profile.logo && (
        <img src={profile.logo} alt="" style={{ height: '18mm', maxWidth: '45mm', objectFit: 'contain' }} />
      )}
      <div style={{ flex: 1, whiteSpace: 'pre-line' }}>
        <div style={{ fontWeight: 700, fontSize: 14 }}>{first}</div>
        {rest.join('\n')}
      </div>
      {aside && <div style={{ whiteSpace: 'pre-line', textAlign: 'right' }}>{aside}</div>}
    </div>
  )
}

function Title({ children }: { children: ReactNode }) {
  return <h2 style={{ textAlign: 'center', margin: '3mm 0 2mm', fontSize: 18 }}>{children}</h2>
}

/** Bảng thông tin 2 cột (nhãn: giá trị), không viền. */
function InfoGrid({ items }: { items: [string, ReactNode][] }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: '6mm', marginBottom: '2mm' }}>
      {items.map(([label, value]) => (
        <div key={label}>
          {label}: <b>{value}</b>
        </div>
      ))}
    </div>
  )
}

function Signatures({ roles }: { roles: string[] }) {
  return (
    <table style={{ width: '100%', marginTop: '4mm', textAlign: 'center', tableLayout: 'fixed' }}>
      <tbody>
        <tr>
          {roles.map((r) => (
            <td key={r}>
              <b>{r}</b>
              <div style={{ fontSize: 11, fontStyle: 'italic' }}>(Ký, ghi rõ họ tên)</div>
              <div style={{ height: '22mm' }} />
            </td>
          ))}
        </tr>
      </tbody>
    </table>
  )
}

function Toolbar() {
  return (
    <Button type="primary" onClick={() => window.print()}>
      In / Lưu PDF
    </Button>
  )
}

function useParamsTrip() {
  const { tripId } = useParams()
  return tripId!
}

export function PickingListPrint() {
  const tripId = useParamsTrip()
  const profile = usePrintProfile()
  const picking = useQuery({
    queryKey: ['picking', tripId],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/trips/{trip_id}/picking-list', { params: { path: { trip_id: tripId } } })),
  })
  const traffic = useQuery({
    queryKey: ['trip', tripId, 'traffic'],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/trips/{trip_id}/traffic', { params: { path: { trip_id: tripId } } })),
  })
  const [printedAt] = useState(() => new Date().toISOString())
  const docs = useMemo(
    () =>
      profile.data && picking.data && traffic.isFetched
        ? [pickingDoc(profile.data, picking.data, traffic.data?.notices ?? [], printedAt)]
        : null,
    [profile.data, picking.data, traffic.data, traffic.isFetched, printedAt],
  )
  if (!docs) return <Spin />
  return <PagedDocuments docs={docs} toolbar={<Toolbar />} />
}

function pickingDoc(profile: Profile, data: Picking, notices: string[], printedAt: string): PrintDoc {
  const t = data.trip
  return {
    key: t.id,
    header: (
      <>
        <PrintHeader profile={profile} text={profile.picking_header} aside={`Lệnh: ${t.code}\nNgày giao: ${fmtDate(t.plan_date)}`} />
        <Title>PHIẾU SOẠN HÀNG</Title>
        <InfoGrid
          items={[
            ['Kho xuất', data.warehouse_name],
            ['Xe', `${t.vehicle_code} (lượt ${t.trip_seq})`],
            ['Lái xe', t.driver?.full_name ?? '-'],
            ['Phụ xe', t.assistant?.full_name ?? '-'],
          ]}
        />
      </>
    ),
    cols: (
      <>
        <col style={{ width: '9mm' }} />
        <col style={{ width: '35mm' }} />
        <col />
        <col style={{ width: '17mm' }} />
        <col style={{ width: '19mm' }} />
        <col style={{ width: '20mm' }} />
        <col style={{ width: '24mm' }} />
        <col style={{ width: '13mm' }} />
        <col style={{ width: '14mm' }} />
      </>
    ),
    head: (
      <tr>
        {['#', 'Mã hàng', 'Tên hàng', 'Nhóm', 'SL SKU', 'SL ĐVT', 'Chẵn + lẻ', 'Kg', 'Thực xuất'].map((h) => (
          <th key={h} style={th}>
            {h}
          </th>
        ))}
      </tr>
    ),
    rows: data.lines.map((l, i) => (
      <tr key={`${l.product_code}-${i}`}>
        <td style={right}>{i + 1}</td>
        <td style={code}>{l.product_code}</td>
        <td style={cell}>{l.product_name}</td>
        <td style={code}>{TEMP_GROUP[l.temp_group]}</td>
        <td style={right}>
          {fmtNumber(l.sku_qty)} {l.sku_uom}
        </td>
        <td style={right}>
          {fmtNumber(l.uom_qty)} {l.uom}
        </td>
        <td style={cell}>{packText(l) ?? '-'}</td>
        <td style={right}>{fmtNumber(l.weight_kg)}</td>
        <td style={cell} />
      </tr>
    )),
    tail: (
      <div style={{ marginTop: '2mm' }}>
        {data.adhoc_items.length > 0 && <div>Hàng khác: {data.adhoc_items.join('; ')}</div>}
        {notices.map((n) => (
          <div key={n} style={{ fontStyle: 'italic' }}>
            {n}
          </div>
        ))}
        <Signatures roles={['Người lập', 'Thủ kho', 'Lái xe']} />
        <div style={{ fontSize: 11 }}>In lúc {fmtDateTime(printedAt)}</div>
      </div>
    ),
    footer: profile.picking_footer,
  }
}

export function DeliveryNotesPrint() {
  const tripId = useParamsTrip()
  const profile = usePrintProfile()
  const notes = useQuery({
    queryKey: ['delivery-notes', tripId],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/trips/{trip_id}/delivery-notes', { params: { path: { trip_id: tripId } } })),
  })
  const [printedAt] = useState(() => new Date().toISOString())
  const docs = useMemo(
    () =>
      profile.data && notes.data
        ? notes.data.notes.map((n, i) => deliveryDoc(profile.data, notes.data, n, i, printedAt))
        : null,
    [profile.data, notes.data, printedAt],
  )
  if (!docs) return <Spin />
  if (!docs.length) return <p style={{ padding: 24 }}>Lệnh không có hàng cần giao.</p>
  return (
    <PagedDocuments
      docs={docs}
      toolbar={
        <span>
          {docs.length} phiếu · <Toolbar />
        </span>
      }
    />
  )
}

function deliveryDoc(profile: Profile, data: Notes, n: Note, index: number, printedAt: string): PrintDoc {
  const t = data.trip
  const customer = n.customer_code ? `${n.customer_code} - ${n.customer_name}` : (n.customer_name ?? '-')
  const contact = [n.contact_name, n.phone].filter(Boolean).join(' - ')
  return {
    key: `${n.stop_seq}-${n.order_ref ?? `adhoc-${index}`}`,
    header: (
      <>
        <PrintHeader
          profile={profile}
          text={profile.delivery_header}
          aside={`${n.order_ref ? `Số đơn: ${n.order_ref}\n` : ''}Ngày giao: ${fmtDate(t.plan_date)}`}
        />
        <Title>PHIẾU GIAO HÀNG</Title>
        <div style={{ marginBottom: '1mm' }}>
          Khách hàng: <b>{customer}</b>
        </div>
        <div style={{ marginBottom: '1mm' }}>
          Địa chỉ giao: <b>{n.address ?? '-'}</b>
        </div>
        <InfoGrid
          items={[
            ['Người liên hệ', contact || '-'],
            ['Ngày đặt', n.order_date ? fmtDate(n.order_date) : '-'],
            ['Kho xuất', data.warehouse_name],
            ['Lệnh giao', `${t.code} (điểm ${n.stop_seq})`],
            ['Xe', `${t.vehicle_code} - ${data.vehicle_plate}`],
            ['Lái xe', [t.driver?.full_name, t.driver?.phone].filter(Boolean).join(' - ') || '-'],
          ]}
        />
        {n.order_note && <div style={{ marginBottom: '1mm' }}>Ghi chú: {n.order_note}</div>}
      </>
    ),
    cols: (
      <>
        <col style={{ width: '9mm' }} />
        <col style={{ width: '35mm' }} />
        <col />
        <col style={{ width: '18mm' }} />
        <col style={{ width: '25mm' }} />
        <col style={{ width: '13mm' }} />
        <col style={{ width: '20mm' }} />
        <col style={{ width: '14mm' }} />
      </>
    ),
    head: (
      <tr>
        {['STT', 'Mã hàng', 'Tên hàng', 'Số lượng', 'Quy đổi', 'Kg', 'Thành tiền', 'Thực nhận'].map((h) => (
          <th key={h} style={th}>
            {h}
          </th>
        ))}
      </tr>
    ),
    rows: [
      ...n.lines.map((l, i) => (
        <tr key={`${l.product_code}-${i}`}>
          <td style={right}>{i + 1}</td>
          <td style={code}>{l.product_code}</td>
          <td style={cell}>{l.product_name}</td>
          <td style={right}>
            {fmtNumber(l.sku_qty)} {l.sku_uom}
          </td>
          <td style={cell}>{packText(l) ?? `${fmtNumber(l.uom_qty)} ${l.uom}`}</td>
          <td style={right}>{fmtNumber(l.weight_kg)}</td>
          <td style={right}>{l.amount === null ? '' : fmtNumber(l.amount)}</td>
          <td style={cell} />
        </tr>
      )),
      ...n.adhoc_items.map((a, i) => (
        <tr key={`adhoc-${i}`}>
          <td style={right}>{n.lines.length + i + 1}</td>
          <td style={cell} />
          <td style={cell} colSpan={4}>
            {a}
          </td>
          <td style={cell} />
          <td style={cell} />
        </tr>
      )),
    ],
    tail: (
      <div style={{ marginTop: '2mm' }}>
        <div style={{ textAlign: 'right' }}>
          Tổng giá trị: <b>{fmtNumber(n.total_value)} đ</b>
        </div>
        <Signatures roles={['Thủ kho', 'Lái xe', 'Khách hàng']} />
        <div style={{ fontSize: 11 }}>In lúc {fmtDateTime(printedAt)}</div>
      </div>
    ),
    footer: profile.delivery_footer,
  }
}
