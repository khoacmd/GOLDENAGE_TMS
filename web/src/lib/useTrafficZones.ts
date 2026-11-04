import { useQuery } from '@tanstack/react-query'

import { api } from '../api'
import { unwrap } from './api-helpers'
import type { MapZone } from './MapView'

/** Vùng hạn chế lưu hành đang hiệu lực, vẽ trên bản đồ kế hoạch và chi tiết lệnh. */
export function useTrafficZones(): MapZone[] | undefined {
  const query = useQuery({
    queryKey: ['traffic-zones'],
    staleTime: 3_600_000,
    queryFn: async () => unwrap(await api.GET('/api/v1/traffic/zones')),
  })
  return query.data
}
