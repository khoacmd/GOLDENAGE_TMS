import { errorMessage } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Box, Button, Page, Spinner, Text, useNavigate } from 'zmp-ui'

import { api } from '../../lib/api'
import { TRIP_STATUS, today } from '../../lib/format'
import { useSession } from '../../lib/useSession'
import { DayNav } from '../DayNav'
import { StatusTag } from '../StatusTag'

/** Chuyến được phân công theo ngày (kênh phụ, ứng dụng TMS vẫn là kênh chính). */
export function DriverTripsPage() {
  const navigate = useNavigate()
  const { state, setActivating, switchAccount } = useSession()
  const [day, setDay] = useState(today)
  const trips = useQuery({
    queryKey: ['driver-trips', day],
    refetchInterval: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/driver/trips', { params: { query: { plan_date: day } } })
      if (!data) throw new Error(errorMessage(error, 'Không tải được chuyến'))
      return data
    },
  })
  const company = state.status === 'ready' ? state.account.company.name : ''

  return (
    <Page className="screen">
      <Box p={4} className="heading">
        <Text.Title size="large">Chuyến của tôi</Text.Title>
        <Text className="muted">{company}</Text>
      </Box>
      <DayNav day={day} onChange={setDay} canReset={day !== today()} onReset={() => setDay(today())} />
      {trips.isLoading && (
        <Box className="center">
          <Spinner />
        </Box>
      )}
      {trips.isError && (
        <Box p={4} className="center">
          <Text>{trips.error.message}</Text>
          <Box mt={2}>
            <Button size="small" onClick={() => void trips.refetch()}>
              Thử lại
            </Button>
          </Box>
        </Box>
      )}
      {trips.data?.length === 0 && (
        <Box p={6} className="center">
          <Text className="muted">Không có chuyến trong ngày này.</Text>
        </Box>
      )}
      {trips.data?.map((trip) => (
        <button key={trip.id} className="card row-button" onClick={() => navigate(`/trips/${trip.id}`)}>
          <div className="row-between">
            <Text bold>{trip.code}</Text>
            <StatusTag {...(TRIP_STATUS[trip.order_status] ?? { label: trip.order_status, color: '#6b7280' })} />
          </div>
          <Text size="small" className="muted">
            {trip.vehicle_code} · lượt {trip.trip_seq} · Kho {trip.warehouse_code}
          </Text>
        </button>
      ))}
      <div className="footer-links">
        <button className="link-button" onClick={() => setActivating(true)}>
          Nhập mã kích hoạt khác
        </button>
        <button className="link-button" onClick={switchAccount}>
          Đổi tài khoản
        </button>
      </div>
    </Page>
  )
}
