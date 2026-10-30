import type { components } from '@tms/api-client'
import dayjs from 'dayjs'

type S = components['schemas']

export type Trip = S['TripOut']
export type TripSummary = S['TripSummaryOut']

export const toISODate = (d: dayjs.Dayjs) => d.format('YYYY-MM-DD')

/** Ngày lập kế hoạch mặc định: ngày mai. */
export const defaultPlanDate = () => toISODate(dayjs().add(1, 'day'))

export function cargoCompatible(cargo: S['CargoClass'], group: S['TempGroup']) {
  return cargo === 'ANY' || (cargo === 'DRY_ONLY' ? group === 'DRY' : group === 'COLD')
}

export function vehicleMatches(req: S['VehicleRequirement'], type: S['VehicleType']) {
  return req === 'ANY' || req === type
}

export const loadPercent = (weight: number | string, capacity: number | string) =>
  Math.round((Number(weight) / Number(capacity)) * 100)
