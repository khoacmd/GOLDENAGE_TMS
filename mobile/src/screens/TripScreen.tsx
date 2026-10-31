import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Linking, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native'

import { api } from '../api'
import { ITEM_STATUS, TEMP_GROUP, TRIP_STATUS, fmtDate, fmtNumber } from '../lib/format'
import { Badge, Button, Card, Header, colors } from '../lib/ui'
import { useQueue } from '../lib/useQueue'
import { discard, processQueue, retry } from '../queue'

export type Trip = components['schemas']['TripOut']
export type Stop = components['schemas']['TripStopOut']
export type Item = components['schemas']['TripItemOut']

export function TripScreen({
  tripId,
  onBack,
  onConfirm,
}: {
  tripId: string
  onBack: () => void
  onConfirm: (trip: Trip, stop: Stop, item: Item) => void
}) {
  const queryClient = useQueryClient()
  const queue = useQueue()
  const query = useQuery({
    queryKey: ['driver-trip', tripId],
    queryFn: async () => {
      const { data } = await api.GET('/api/v1/driver/trips/{trip_id}', { params: { path: { trip_id: tripId } } })
      if (!data) throw new Error('Không tải được chuyến')
      return data
    },
  })
  const start = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/v1/trips/{trip_id}/dispatch', { params: { path: { trip_id: tripId } } })
      if (!data) throw new Error((error as { error?: { message?: string } })?.error?.message ?? 'Không xuất phát được')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries(),
    onError: (e: Error) => Alert.alert('Lỗi', e.message),
  })

  const trip = query.data
  if (!trip) return <Header title={query.isError ? 'Lỗi tải chuyến' : 'Đang tải…'} onBack={onBack} />
  const status = TRIP_STATUS[trip.order_status] ?? { label: trip.order_status, color: colors.muted }
  const queued = new Map(queue.filter((q) => q.tripId === trip.id).map((q) => [q.itemId, q]))

  const openMap = (stop: Stop) =>
    void Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${stop.latitude},${stop.longitude}`)

  return (
    <View style={styles.screen}>
      <Header title={`Chuyến ${trip.code}`} onBack={onBack} />
      <ScrollView
        refreshControl={
          <RefreshControl
            refreshing={query.isFetching}
            onRefresh={() => {
              void processQueue()
              void query.refetch()
            }}
          />
        }
        contentContainerStyle={{ paddingBottom: 32 }}
      >
        <Card>
          <View style={styles.row}>
            <Text style={styles.bold}>{fmtDate(trip.plan_date)}</Text>
            <Badge label={status.label} color={status.color} />
          </View>
          <Text>
            {trip.vehicle_code} - {trip.vehicle_name} · lượt {trip.trip_seq}
          </Text>
          <Text>
            Kho {trip.warehouse_code} - {trip.warehouse_name}
          </Text>
          <Text style={styles.muted}>
            Lái xe {trip.driver?.full_name ?? '-'}
            {trip.assistant ? ` · Phụ xe ${trip.assistant.full_name}` : ''} · {fmtNumber(trip.total_weight_kg)} kg
          </Text>
          {trip.order_status === 'PICKED' && (
            <Button title="Nhận hàng & xuất phát" loading={start.isPending} onPress={() => start.mutate()} />
          )}
          {trip.order_status === 'APPROVED' && <Text style={styles.muted}>Thủ kho đang soạn hàng.</Text>}
          {trip.order_status === 'PREPARED' && <Text style={styles.muted}>Đã soạn hàng, chờ thủ kho xác nhận xuất kho.</Text>}
        </Card>

        {trip.stops.map((stop) => (
          <Card key={stop.id}>
            <View style={styles.row}>
              <Text style={[styles.bold, { flex: 1 }]}>
                {stop.seq}. {stop.customer_code ? `${stop.customer_code} - ${stop.customer_name}` : stop.name}
              </Text>
              <Text style={{ color: colors.primary }} onPress={() => openMap(stop)}>
                Chỉ đường
              </Text>
            </View>
            <Text style={styles.muted}>{stop.address}</Text>
            {stop.items.map((item) => {
              const q = queued.get(item.id)
              const st = ITEM_STATUS[item.status]
              return (
                <View key={item.id} style={styles.item}>
                  <View style={styles.row}>
                    <Text style={{ flex: 1 }}>
                      {item.external_ref ? `${item.external_ref} · ${TEMP_GROUP[item.temp_group ?? 'DRY']}` : item.description} ·{' '}
                      {fmtNumber(item.weight_kg)} kg
                    </Text>
                    {q ? (
                      <Badge
                        label={q.state === 'pending' ? 'Chờ gửi' : q.state === 'error' ? 'Lỗi gửi' : 'Bị từ chối'}
                        color={q.state === 'pending' ? '#fa8c16' : colors.danger}
                      />
                    ) : (
                      <Badge label={st.label} color={st.color} />
                    )}
                  </View>
                  {item.reason && <Text style={styles.muted}>Lý do: {item.reason}</Text>}
                  {q && q.state !== 'pending' && (
                    <View style={{ gap: 4 }}>
                      {q.messages.map((m) => (
                        <Text key={m} style={{ color: colors.danger }}>
                          • {m}
                        </Text>
                      ))}
                      {q.state === 'error' && <Button title="Gửi lại" onPress={() => retry(q.clientId)} />}
                      <Button kind="outline" title="Bỏ và xác nhận lại" onPress={() => discard(q.clientId)} />
                    </View>
                  )}
                  {!q && item.status === 'PENDING' && trip.order_status === 'DISPATCHED' && (
                    <Button title="Xác nhận giao" onPress={() => onConfirm(trip, stop, item)} />
                  )}
                </View>
              )
            })}
          </Card>
        ))}
      </ScrollView>
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#f2f3f5' },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  bold: { fontSize: 16, fontWeight: '700' },
  muted: { color: colors.muted },
  item: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 8, marginTop: 6, gap: 6 },
})
