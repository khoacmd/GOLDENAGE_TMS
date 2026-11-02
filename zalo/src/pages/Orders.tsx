import { errorMessage } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Box, Button, Icon, Page, Spinner, Text, useNavigate } from 'zmp-ui'

import { api } from '../lib/api'
import { dayLabel, etaText, money, ORDER_STATUS, shiftDay, time } from '../lib/format'
import { useSession } from '../lib/useSession'
import { StatusTag } from './StatusTag'

/** Đơn theo ngày giao; mặc định hôm nay (server tính theo múi giờ công ty). */
export function OrdersPage() {
  const navigate = useNavigate()
  const { state, setActivating, switchAccount } = useSession()
  const [day, setDay] = useState<string | null>(null)
  const query = useQuery({
    queryKey: ['orders', day],
    refetchInterval: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/customer/orders', {
        params: { query: day ? { date: day } : {} },
      })
      if (!data) throw new Error(errorMessage(error, 'Không tải được đơn hàng'))
      return data
    },
  })
  const shown = query.data?.date
  const company = state.status === 'ready' ? state.account.company.name : ''

  return (
    <Page className="screen">
      <Box p={4} className="heading">
        <Text.Title size="large">Đơn hàng</Text.Title>
        <Text className="muted">{company}</Text>
      </Box>
      <div className="day-nav">
        <button aria-label="Ngày trước" disabled={!shown} onClick={() => shown && setDay(shiftDay(shown, -1))}>
          <Icon icon="zi-chevron-left" />
        </button>
        <label className="day-label">
          <Text bold>{shown ? dayLabel(shown) : '...'}</Text>
          <input
            type="date"
            aria-label="Chọn ngày giao"
            value={shown ?? ''}
            onChange={(e) => e.target.value && setDay(e.target.value)}
          />
        </label>
        <button aria-label="Ngày sau" disabled={!shown} onClick={() => shown && setDay(shiftDay(shown, 1))}>
          <Icon icon="zi-chevron-right" />
        </button>
      </div>
      {day && (
        <button className="link-button" onClick={() => setDay(null)}>
          Về hôm nay
        </button>
      )}

      {query.isLoading && (
        <Box className="center">
          <Spinner />
        </Box>
      )}
      {query.isError && (
        <Box p={4} className="center">
          <Text>{query.error.message}</Text>
          <Box mt={2}>
            <Button size="small" onClick={() => void query.refetch()}>
              Thử lại
            </Button>
          </Box>
        </Box>
      )}
      {query.data?.items.length === 0 && (
        <Box p={6} className="center">
          <Text className="muted">Không có đơn hàng trong ngày này.</Text>
        </Box>
      )}
      {query.data?.items.map((order) => (
        <button key={order.id} className="card row-button" onClick={() => navigate(`/orders/${order.id}`)}>
          <div className="row-between">
            <Text bold>{order.external_ref}</Text>
            <StatusTag {...ORDER_STATUS[order.status]} />
          </div>
          <Text size="small" className="muted">
            {order.customer_name} · Điểm {order.delivery_point_name ?? order.delivery_point_code}
          </Text>
          {order.eta && (
            <Text size="small" className="eta">
              Dự kiến đến {etaText(order.eta)}
            </Text>
          )}
          {order.delivered_at && (
            <Text size="small" className="muted">
              Giao lúc {time(order.delivered_at)}
            </Text>
          )}
          <div className="row-between">
            <Text size="small" className="muted">
              {order.line_count} mặt hàng
            </Text>
            {order.order_value !== null && <Text size="small">{money(order.order_value)}</Text>}
          </div>
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
