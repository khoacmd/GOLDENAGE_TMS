import * as Location from 'expo-location'

import TmsLocation from '../../modules/tms-location'

export interface Position {
  latitude: number
  longitude: number
  accuracy: number | null
  mocked: boolean
}

// Vị trí cũ hơn mức này coi như không có (tránh xác nhận bằng vị trí ở điểm trước).
const MAX_AGE_MS = 5 * 60_000
const TIMEOUT_MS = 15_000

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([promise, new Promise<T>((_, reject) => setTimeout(() => reject(new Error('Hết thời gian lấy vị trí')), ms))])
}

/**
 * Vị trí hiện tại: expo-location (Fused Location của Google Play Services), lỗi thì dùng
 * LocationManager của Android qua module `tms-location` (máy không có Play Services).
 */
export async function currentPosition(): Promise<Position | null> {
  const perm = await Location.requestForegroundPermissionsAsync()
  if (perm.status !== 'granted') return null
  try {
    const pos = await withTimeout(Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }), TIMEOUT_MS)
    return { ...pos.coords, mocked: pos.mocked ?? false }
  } catch (e) {
    console.warn('expo-location không lấy được vị trí, dùng định vị dự phòng', e)
  }
  if (TmsLocation) {
    try {
      const pos = await TmsLocation.getCurrentPosition(TIMEOUT_MS)
      if (pos && pos.ageMs <= MAX_AGE_MS) return pos
    } catch (e) {
      console.warn('Định vị dự phòng lỗi', e)
    }
    return null
  }
  // Expo Go: không có module dự phòng.
  const last = await Location.getLastKnownPositionAsync({ maxAge: MAX_AGE_MS }).catch(() => null)
  return last ? { ...last.coords, mocked: last.mocked ?? false } : null
}
