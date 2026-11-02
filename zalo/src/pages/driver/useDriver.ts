import { errorMessage } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'

import { api } from '../../lib/api'

export function useTrip(tripId: string) {
  return useQuery({
    queryKey: ['driver-trip', tripId],
    refetchInterval: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/driver/trips/{trip_id}', {
        params: { path: { trip_id: tripId } },
      })
      if (!data) throw new Error(errorMessage(error, 'Không tải được chuyến'))
      return data
    },
  })
}

export function useRules() {
  return useQuery({
    queryKey: ['driver-rules'],
    staleTime: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/driver/rules')
      if (!data) throw new Error(errorMessage(error, 'Không tải được quy tắc giao hàng'))
      return data
    },
  })
}
