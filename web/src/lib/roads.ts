import { useQueries } from '@tanstack/react-query'

import { api } from '../api'
import { unwrap } from './api-helpers'
import type { MapRoute } from './MapView'

/**
 * Thay đường thẳng của các lệnh (route.id = id lệnh) bằng tuyến theo đường thực tế (OSRM).
 * Khi đang tải hoặc server chưa có OSRM thì giữ đường thẳng nét đứt.
 */
export function useTripRoads(routes: MapRoute[]): MapRoute[] {
  const results = useQueries({
    queries: routes.map((r) => ({
      // Đổi thứ tự / điểm dừng → khóa đổi → tải lại.
      queryKey: ['trip-route', r.id, r.coords.flat().join(',')],
      queryFn: async () =>
        unwrap(await api.GET('/api/v1/trips/{trip_id}/route', { params: { path: { trip_id: r.id } } })),
      staleTime: Infinity,
      retry: false,
    })),
  })
  return routes.map((r, i) => {
    const road = results[i].data
    return road?.road ? { ...r, coords: road.coordinates as [number, number][], dashed: false } : { ...r, dashed: true }
  })
}
