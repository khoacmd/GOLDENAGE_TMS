import type { CSSProperties } from 'react'

/** Bảng in: viền đen liền (máy in kim), độ rộng cột cố định theo `<col>`. */
export const printTable: CSSProperties = { width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }
export const printCell: CSSProperties = {
  border: '1px solid #000',
  padding: '2px 4px',
  verticalAlign: 'top',
  overflowWrap: 'anywhere',
}
