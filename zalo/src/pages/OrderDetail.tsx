import { errorMessage, type components } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { lazy, Suspense, useState } from 'react'
import { Box, Button, Header, ImageViewer, Page, Spinner, Text, useParams } from 'zmp-ui'

import { api } from '../lib/api'
import { ATTEMPT_STATUS, dateTime, etaText, money, ORDER_STATUS, quantity, TEMP_GROUP } from '../lib/format'
import { callPhone, openZalo } from '../lib/zalo'
import { MapBoundary } from './MapBoundary'
import { StatusTag } from './StatusTag'

type Attempt = components['schemas']['CustomerDeliveryAttempt']

// Bản đồ nặng: chỉ tải khi có chuyến đã xuất phát.
const RouteMap = lazy(() => import('./RouteMap'))

function AttemptCard({ attempt, onPhoto }: { attempt: Attempt; onPhoto(urls: string[], index: number): void }) {
  return (
    <div className="log-entry">
      <div className="row-between">
        <Text bold size="small">
          {TEMP_GROUP[attempt.temp_group] ?? attempt.temp_group} · {attempt.trip_code}
        </Text>
        <Text size="small">{ATTEMPT_STATUS[attempt.status]}</Text>
      </div>
      {attempt.eta && (
        <Text size="small" className="eta">
          Dự kiến đến {etaText(attempt.eta)}
        </Text>
      )}
      {attempt.dispatched_at && (
        <Text size="small" className="muted">
          Xuất phát: {dateTime(attempt.dispatched_at)}
        </Text>
      )}
      {attempt.delivered_at && (
        <Text size="small" className="muted">
          {attempt.status === 'FAILED' ? 'Thời gian' : 'Giao lúc'}: {dateTime(attempt.delivered_at)}
        </Text>
      )}
      {attempt.reason && <Text size="small">Lý do: {attempt.reason}</Text>}
      {attempt.driver_name && (
        <Text size="small" className="muted">
          Tài xế: {attempt.driver_name}
        </Text>
      )}
      {attempt.driver_contacts.map((contact) => (
        <div key={contact.name} className="contact">
          <Text size="small">
            {contact.is_assistant ? 'Phụ xe' : 'Tài xế'} {contact.name}
          </Text>
          {contact.phone ? (
            <span className="contact-actions">
              <Button size="small" variant="secondary" onClick={() => callPhone(contact.phone!)}>
                Gọi
              </Button>
              <Button size="small" variant="secondary" onClick={() => openZalo(contact.phone!)}>
                Zalo
              </Button>
            </span>
          ) : (
            <Text size="small" className="muted">
              Chưa có số điện thoại
            </Text>
          )}
        </div>
      ))}
      {attempt.photo_urls.length > 0 && (
        <div className="photos">
          {attempt.photo_urls.map((url, index) => (
            <img key={url} src={url} alt="Chứng từ giao hàng" onClick={() => onPhoto(attempt.photo_urls, index)} />
          ))}
        </div>
      )}
    </div>
  )
}

export function OrderDetailPage() {
  const { id = '' } = useParams()
  const [viewer, setViewer] = useState<{ urls: string[]; index: number } | null>(null)
  const params = { params: { path: { order_id: id } } }
  const detail = useQuery({
    queryKey: ['order', id],
    refetchInterval: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/customer/orders/{order_id}', params)
      if (!data) throw new Error(errorMessage(error, 'Không tải được đơn hàng'))
      return data
    },
  })
  const routes = useQuery({
    queryKey: ['order-routes', id],
    refetchInterval: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/customer/orders/{order_id}/routes', params)
      if (!data) throw new Error(errorMessage(error, 'Không tải được tuyến xe'))
      return data
    },
  })
  const order = detail.data

  return (
    <Page className="screen with-header">
      <Header title={order?.external_ref ?? 'Đơn hàng'} />
      {detail.isLoading && (
        <Box className="center">
          <Spinner />
        </Box>
      )}
      {detail.isError && (
        <Box p={4} className="center">
          <Text>{detail.error.message}</Text>
        </Box>
      )}
      {order && (
        <>
          <div className="card">
            <div className="row-between">
              <Text bold>{order.external_ref}</Text>
              <StatusTag {...ORDER_STATUS[order.status]} />
            </div>
            <Text size="small">{order.customer_name}</Text>
            <Text size="small" className="muted">
              {order.delivery_point_name ?? order.delivery_point_code}: {order.delivery_address}
            </Text>
            {order.eta && (
              <Text className="eta" bold>
                Dự kiến đến {etaText(order.eta)}
              </Text>
            )}
            {order.note && <Text size="small">Ghi chú: {order.note}</Text>}
          </div>

          {routes.data?.map((route) => (
            <div className="card" key={route.trip_code}>
              <Text bold>Tuyến xe {route.trip_code}</Text>
              <Text size="small" className="muted">
                {route.reached ? 'Xe đã đến điểm giao của bạn' : 'Đường xe đã đi đến hiện tại'}
              </Text>
              <MapBoundary>
                <Suspense fallback={<div className="map-placeholder" />}>
                  <RouteMap route={route} />
                </Suspense>
              </MapBoundary>
            </div>
          ))}

          <div className="card">
            <Text bold>Mặt hàng</Text>
            {order.lines.map((line) => (
              <div className="row-between line" key={line.product_code}>
                <Text size="small">{line.product_name}</Text>
                <Text size="small" className="nowrap">
                  {quantity(line.qty)} {line.uom}
                  {line.amount !== null && ` · ${money(line.amount)}`}
                </Text>
              </div>
            ))}
            {order.order_value !== null && (
              <div className="row-between line">
                <Text bold size="small">
                  Giá trị đơn
                </Text>
                <Text bold size="small">
                  {money(order.order_value)}
                </Text>
              </div>
            )}
          </div>

          <div className="card">
            <Text bold>Lịch sử giao</Text>
            {order.deliveries.length === 0 && (
              <Text size="small" className="muted">
                Chưa có lượt giao nào.
              </Text>
            )}
            {order.deliveries.map((attempt, index) => (
              <AttemptCard
                key={`${attempt.trip_code}-${attempt.temp_group}-${index}`}
                attempt={attempt}
                onPhoto={(urls, photo) => setViewer({ urls, index: photo })}
              />
            ))}
          </div>
        </>
      )}
      <ImageViewer
        visible={viewer !== null}
        activeIndex={viewer?.index ?? 0}
        images={(viewer?.urls ?? []).map((src) => ({ src, alt: 'Chứng từ giao hàng' }))}
        onClose={() => setViewer(null)}
      />
    </Page>
  )
}
