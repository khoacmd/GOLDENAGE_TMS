import { Fragment, useCallback, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'

import { printTable } from './printStyles'

/**
 * Chia phiếu in thành các trang A4 cố định (in kim / laser), mỗi phiếu đánh số trang riêng
 * "Trang x/y" ở chân trang. Trình duyệt không đánh số trang theo từng phiếu được, nên đo chiều cao
 * từng phần trên màn hình rồi tự xếp dòng vào trang; phần cuối (tổng, chữ ký) không bị tách trang.
 */

export interface PrintDoc {
  key: string
  /** Đầu phiếu (logo, tiêu đề, thông tin chung), chỉ ở trang đầu. */
  header: ReactNode
  /** `<col>` cố định độ rộng (mm) để đo và in cùng một bố cục. */
  cols: ReactNode
  /** Dòng `<tr>` của tiêu đề bảng, lặp lại ở mỗi trang. */
  head: ReactNode
  rows: ReactNode[]
  /** Phần cuối (tổng, ghi chú, chữ ký), giữ nguyên trên trang cuối. */
  tail: ReactNode
  /** Nội dung chân trang (bên trái), số trang ở bên phải. */
  footer: ReactNode
}

const PAGE_W = 210
const PAGE_H = 296 // 297 mm trừ 1 mm để trình duyệt không đẩy sang trang trắng
const PAD_X = 12
const PAD_Y = 10
// Chừa sai khác nhỏ giữa bố cục màn hình và bố cục khi in.
const SAFETY = 0.97

const pageStyle: CSSProperties = {
  width: `${PAGE_W}mm`,
  height: `${PAGE_H}mm`,
  padding: `${PAD_Y}mm ${PAD_X}mm`,
  boxSizing: 'border-box',
  position: 'relative',
  overflow: 'hidden',
  background: '#fff',
  color: '#000',
  fontFamily: 'Arial, Helvetica, sans-serif',
  fontSize: 12,
  lineHeight: 1.35,
}

const CSS = `
@page { size: A4; margin: 0 }
.print-page { margin: 0 auto 8mm; box-shadow: 0 1px 6px rgba(0,0,0,.25) }
@media print {
  html, body { background: #fff !important; margin: 0 }
  .no-print { display: none !important }
  .print-root { padding: 0 !important; background: #fff !important; min-height: 0 !important }
  .print-page { margin: 0; box-shadow: none; break-after: page; page-break-after: always }
  .print-page:last-child { break-after: auto; page-break-after: auto }
}
`

interface Measure {
  mm: number // px trên 1 mm
  header: number
  head: number
  rows: number[]
  tail: number
  footer: number
}

interface Page {
  first: boolean
  rows: number[]
  tail: boolean
}

function paginate(m: Measure): Page[] {
  const avail = ((PAGE_H - 2 * PAD_Y) * m.mm - m.footer) * SAFETY
  const pages: Page[] = []
  let page: Page = { first: true, rows: [], tail: false }
  let used = m.header + (m.rows.length ? m.head : 0)
  m.rows.forEach((h, i) => {
    if (used + h > avail && page.rows.length) {
      pages.push(page)
      page = { first: false, rows: [], tail: false }
      used = m.head
    }
    page.rows.push(i)
    used += h
  })
  if (used + m.tail > avail && (page.rows.length || !page.first)) {
    pages.push(page)
    page = { first: false, rows: [], tail: false }
  }
  page.tail = true
  pages.push(page)
  return pages
}

function Table({ doc, rows }: { doc: PrintDoc; rows: ReactNode[] }) {
  return (
    <table style={printTable}>
      <colgroup>{doc.cols}</colgroup>
      <thead>{doc.head}</thead>
      <tbody>{rows}</tbody>
    </table>
  )
}

/** Đo 1 phiếu ở độ rộng nội dung trang, trả chiều cao (px) từng phần. */
function Measurer({ doc, onMeasure }: { doc: PrintDoc; onMeasure: (m: Measure) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current!
    const h = (sel: string) => el.querySelector<HTMLElement>(sel)?.getBoundingClientRect().height ?? 0
    onMeasure({
      mm: el.querySelector<HTMLElement>('[data-m=mm]')!.getBoundingClientRect().height / 100,
      header: h('[data-m=header]'),
      head: h('thead'),
      rows: [...el.querySelectorAll('tbody > tr')].map((tr) => tr.getBoundingClientRect().height),
      tail: h('[data-m=tail]'),
      footer: h('[data-m=footer]'),
    })
  }, [doc, onMeasure])
  return (
    <div
      ref={ref}
      aria-hidden
      style={{ ...pageStyle, height: 'auto', position: 'absolute', left: -10000, top: 0, visibility: 'hidden' }}
    >
      <div data-m="mm" style={{ height: '100mm' }} />
      <div data-m="header">{doc.header}</div>
      <Table doc={doc} rows={doc.rows} />
      <div data-m="tail">{doc.tail}</div>
      <div data-m="footer">{doc.footer}</div>
    </div>
  )
}

function Footer({ children, page, pages }: { children: ReactNode; page: number; pages: number }) {
  return (
    <div style={{ position: 'absolute', left: `${PAD_X}mm`, right: `${PAD_X}mm`, bottom: `${PAD_Y}mm` }}>
      <div
        style={{ display: 'flex', gap: 12, justifyContent: 'space-between', borderTop: '1px solid #000', paddingTop: 2, fontSize: 11 }}
      >
        <div style={{ whiteSpace: 'pre-line' }}>{children}</div>
        <div style={{ whiteSpace: 'nowrap' }}>
          Trang {page}/{pages}
        </div>
      </div>
    </div>
  )
}

function Doc({ doc }: { doc: PrintDoc }) {
  // Đo lại khi phiếu đổi (dữ liệu tải xong, đổi mẫu đầu/chân trang).
  const [measured, setMeasured] = useState<{ doc: PrintDoc; m: Measure } | null>(null)
  const onMeasure = useCallback((m: Measure) => setMeasured({ doc, m }), [doc])
  if (measured?.doc !== doc) return <Measurer doc={doc} onMeasure={onMeasure} />
  const pages = paginate(measured.m)
  return (
    <>
      {pages.map((p, i) => (
        <div key={i} className="print-page" style={pageStyle}>
          {p.first && doc.header}
          {p.rows.length > 0 && <Table doc={doc} rows={p.rows.map((r) => doc.rows[r])} />}
          {p.tail && doc.tail}
          <Footer page={i + 1} pages={pages.length}>
            {doc.footer}
          </Footer>
        </div>
      ))}
    </>
  )
}

export function PagedDocuments({ docs, toolbar }: { docs: PrintDoc[]; toolbar?: ReactNode }) {
  return (
    <div className="print-root" style={{ background: '#e8e8e8', minHeight: '100vh', padding: '8mm 0' }}>
      <style>{CSS}</style>
      <div className="no-print" style={{ width: `${PAGE_W}mm`, maxWidth: '100%', margin: '0 auto 6mm', textAlign: 'right' }}>
        {toolbar}
      </div>
      {docs.map((d) => (
        <Fragment key={d.key}>
          <Doc doc={d} />
        </Fragment>
      ))}
    </div>
  )
}
