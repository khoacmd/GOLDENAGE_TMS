import { requireOptionalNativeModule } from 'expo'

export interface NativePosition {
  latitude: number
  longitude: number
  accuracy: number | null
  timestamp: number
  /** Tuổi của vị trí (ms) - vị trí cũ là vị trí đã biết gần nhất. */
  ageMs: number
  provider: string | null
  mocked: boolean
}

interface TmsLocationModule {
  getCurrentPosition(timeoutMs: number): Promise<NativePosition | null>
}

/** Chỉ có trong bản build (APK), không có trong Expo Go → null. */
export default requireOptionalNativeModule<TmsLocationModule>('TmsLocation')
