import { errorMessage } from '@tms/api-client'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Box, Button, Header, Page, Spinner, Text, useNavigate, useParams } from 'zmp-ui'

import { api } from '../../lib/api'
import { ITEM_STATUS, TEMP_GROUP, TRIP_STATUS } from '../../lib/format'
import { openDirections } from '../../lib/zalo'
import { StatusTag } from '../StatusTag'
import { useRules, useTrip } from './useDriver'

export function DriverTripPage() {
  const { tripId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const query = useTrip(tripId)
  const rules = useRules()
  const start = useMutation({
    mutationFn: async () => {
      const { data, error: err } = await api.POST('/api/v1/trips/{trip_id}/dispatch', {
        params: { path: { trip_id: tripId } },
      })
      if (!data) throw new Error(errorMessage(err, 'Không xuất phát được'))
    },
    onSuccess: () => {
      setError(null)
      return queryClient.invalidateQueries()
    },
    onError: (e: Error) => setError(e.message),
  })
  const trip = query.data
  const canConfirm = rules.data?.zalo_confirm_enabled === true

  return (
    <Page className="screen with-header">
      <Header title={trip ? `Chuyến ${trip.code}` : 'Chuyến'} />
      {query.isLoading && (
        <Box className="center">
          <Spinner />
        </Box>
      )}
      {query.isError && (
        <Box p={4} className="center">
          <Text>{query.error.message}</Text>
        </Box>
      )}
      {trip && (
        <>
          <div className="card">
            <div className="row-between">
              <Text bold>
                {trip.vehicle_code} - {trip.vehicle_name} · lượt {trip.trip_seq}
              </Text>
              <StatusTag {...(TRIP_STATUS[trip.order_status] ?? { label: trip.order_status, color: '#6b7280' })} />
            </div>
            <Text size="small" className="muted">
              Kho {trip.warehouse_code} - {trip.warehouse_name}
            </Text>
            <Text size="small" className="muted">
              Lái xe {trip.driver?.full_name ?? '-'}
              {trip.assistant ? ` · Phụ xe ${trip.assistant.full_name}` : ''}
            </Text>
            {trip.order_status === 'APPROVED' && (
              <Text size="small" className="muted">
                Thủ kho đang soạn hàng.
              </Text>
            )}
            {trip.order_status === 'PREPARED' && (
              <Text size="small" className="muted">
                Đã soạn hàng, chờ thủ kho xác nhận xuất kho.
              </Text>
            )}
            {trip.order_status === 'PICKED' && (
              <Box mt={2}>
                <Button fullWidth loading={start.isPending} onClick={() => start.mutate()}>
                  Nhận hàng & xuất phát
                </Button>
              </Box>
            )}
            {error && <Text className="error-text">{error}</Text>}
            {rules.data && !canConfirm && trip.order_status === 'DISPATCHED' && (
              <Text size="small" className="muted">
                Công ty chưa cho phép xác nhận giao qua Zalo, vui lòng dùng ứng dụng TMS.
              </Text>
            )}
          </div>

          {trip.stops.map((stop) => (
            <div className="card" key={stop.id}>
              <div className="row-between">
                <Text bold>
                  {stop.seq}. {stop.customer_code ? `${stop.customer_code} - ${stop.customer_name}` : stop.name}
                </Text>
                {stop.latitude !== null && stop.longitude !== null && (
                  <button className="inline-link" onClick={() => openDirections(stop.latitude!, stop.longitude!)}>
                    Chỉ đường
                  </button>
                )}
              </div>
              <Text size="small" className="muted">
                {stop.address}
              </Text>
              {stop.items.map((item) => (
                <div className="log-entry" key={item.id}>
                  <div className="row-between">
                    <Text size="small">
                      {item.external_ref
                        ? `${item.external_ref} · ${TEMP_GROUP[item.temp_group ?? 'DRY']}`
                        : item.description}{' '}
                      · {Number(item.weight_kg).toLocaleString('vi-VN')} kg
                    </Text>
                    <StatusTag {...ITEM_STATUS[item.status]} />
                  </div>
                  {item.reason && (
                    <Text size="small" className="muted">
                      Lý do: {item.reason}
                    </Text>
                  )}
                  {canConfirm && item.status === 'PENDING' && trip.order_status === 'DISPATCHED' && (
                    <Box mt={1}>
                      <Button size="small" fullWidth onClick={() => navigate(`/trips/${trip.id}/items/${item.id}`)}>
                        Xác nhận giao
                      </Button>
                    </Box>
                  )}
                </div>
              ))}
            </div>
          ))}
        </>
      )}
    </Page>
  )
}
