import { Icon, Text } from 'zmp-ui'

import { dayLabel, shiftDay } from '../lib/format'

/** Chọn ngày: lùi / tiến 1 ngày, bấm vào ngày để mở lịch. */
export function DayNav({
  day,
  onChange,
  canReset,
  onReset,
}: {
  day: string | undefined
  onChange(day: string): void
  canReset: boolean
  onReset(): void
}) {
  return (
    <>
      <div className="day-nav">
        <button aria-label="Ngày trước" disabled={!day} onClick={() => day && onChange(shiftDay(day, -1))}>
          <Icon icon="zi-chevron-left" />
        </button>
        <label className="day-label">
          <Text bold>{day ? dayLabel(day) : '...'}</Text>
          <input
            type="date"
            aria-label="Chọn ngày"
            value={day ?? ''}
            onChange={(e) => e.target.value && onChange(e.target.value)}
          />
        </label>
        <button aria-label="Ngày sau" disabled={!day} onClick={() => day && onChange(shiftDay(day, 1))}>
          <Icon icon="zi-chevron-right" />
        </button>
      </div>
      {canReset && (
        <button className="link-button" onClick={onReset}>
          Về hôm nay
        </button>
      )}
    </>
  )
}
