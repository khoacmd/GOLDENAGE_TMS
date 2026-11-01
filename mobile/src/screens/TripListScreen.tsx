import type { components } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native'

import { api } from '../api'
import { registerDevice } from '../device'
import { TRIP_STATUS, fmtDate, fmtNumber, shiftDate, todayISO } from '../lib/format'
import { Badge, Button, Card, Header, colors } from '../lib/ui'
import { useQueue } from '../lib/useQueue'

type Me = components['schemas']['MeResponse']
type Trip = components['schemas']['TripSummaryOut']

export function TripListScreen({
  me,
  onOpen,
  onChangePassword,
  onLogout,
}: {
  me: Me
  onOpen: (id: string) => void
  onChangePassword: () => void
  onLogout: () => void
}) {
  const [date, setDate] = useState(todayISO)
  const queue = useQueue()
  const isDriver = me.roles.includes('driver')
  const trips = useQuery({
    queryKey: ['driver-trips', date],
    enabled: isDriver,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/driver/trips', { params: { query: { plan_date: date } } })
      if (!data) throw new Error((error as { error?: { message?: string } })?.error?.message ?? 'Không tải được chuyến')
      return data
    },
  })
  // Đăng ký thiết bị mỗi lần mở app; admin công ty có thể yêu cầu duyệt hoặc khóa máy.
  const device = useQuery({ queryKey: ['device'], enabled: isDriver, queryFn: registerDevice, staleTime: 5 * 60_000 })
  const deviceStatus = device.data?.status
  const waiting = queue.filter((q) => q.state === 'pending').length
  const problems = queue.filter((q) => q.state !== 'pending').length

  return (
    <View style={styles.screen}>
      <Header
        title={`Xin chào, ${me.full_name}`}
        right={
          <View style={styles.headerLinks}>
            <Text onPress={onChangePassword} style={{ color: colors.primary }}>
              Đổi mật khẩu
            </Text>
            <Text onPress={onLogout} style={{ color: colors.primary }}>
              Đăng xuất
            </Text>
          </View>
        }
      />
      {!isDriver ? (
        <Card>
          <Text>Tài khoản không có vai trò nhân viên giao hàng.</Text>
        </Card>
      ) : (
        <>
          <View style={styles.dateBar}>
            <Button kind="outline" title="‹" onPress={() => setDate(shiftDate(date, -1))} style={styles.dateBtn} />
            <Text style={styles.date}>{date === todayISO() ? `Hôm nay ${fmtDate(date)}` : fmtDate(date)}</Text>
            <Button kind="outline" title="›" onPress={() => setDate(shiftDate(date, 1))} style={styles.dateBtn} />
          </View>
          {(deviceStatus === 'PENDING' || deviceStatus === 'BLOCKED') && (
            <Card style={{ backgroundColor: '#fff1f0' }}>
              <Text style={{ color: colors.danger }}>
                {deviceStatus === 'PENDING'
                  ? 'Điện thoại này đang chờ admin công ty duyệt - chưa xác nhận giao được.'
                  : 'Điện thoại này đã bị khóa - liên hệ admin công ty.'}
              </Text>
              <Text onPress={() => void device.refetch()} style={{ color: colors.primary, marginTop: 4 }}>
                Kiểm tra lại
              </Text>
            </Card>
          )}
          {(waiting > 0 || problems > 0) && (
            <Card style={{ backgroundColor: '#fff7e6' }}>
              {waiting > 0 && <Text>{waiting} xác nhận đang chờ gửi (sẽ tự gửi khi có mạng)</Text>}
              {problems > 0 && <Text style={{ color: colors.danger }}>{problems} xác nhận bị từ chối - mở chuyến để xem</Text>}
            </Card>
          )}
          <FlatList<Trip>
            data={trips.data ?? []}
            keyExtractor={(t) => t.id}
            refreshControl={<RefreshControl refreshing={trips.isFetching} onRefresh={() => void trips.refetch()} />}
            ListEmptyComponent={
              <Text style={styles.empty}>{trips.isLoading ? 'Đang tải…' : trips.error ? trips.error.message : 'Không có chuyến nào'}</Text>
            }
            renderItem={({ item: t }) => {
              const status = TRIP_STATUS[t.order_status] ?? { label: t.order_status, color: colors.muted }
              const done = (t.item_counts.SUCCESS ?? 0) + (t.item_counts.FAILED ?? 0) + (t.item_counts.CANCELLED ?? 0)
              const total = Object.values(t.item_counts).reduce((a, b) => a + (b ?? 0), 0)
              return (
                <Pressable onPress={() => onOpen(t.id)}>
                  <Card>
                    <View style={styles.row}>
                      <Text style={styles.code}>{t.code}</Text>
                      <Badge label={status.label} color={status.color} />
                    </View>
                    <Text>
                      {t.vehicle_code} - {t.vehicle_name} · lượt {t.trip_seq}
                    </Text>
                    <Text style={styles.muted}>
                      Kho {t.warehouse_code} · {t.stop_count} điểm · {fmtNumber(t.total_weight_kg)} kg · đã xử lý {done}/{total}
                    </Text>
                  </Card>
                </Pressable>
              )
            }}
          />
        </>
      )}
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#f2f3f5' },
  headerLinks: { flexDirection: 'row', gap: 16 },
  dateBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 12 },
  dateBtn: { paddingVertical: 6, paddingHorizontal: 14 },
  date: { fontSize: 16, fontWeight: '600' },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  code: { fontSize: 16, fontWeight: '700' },
  muted: { color: colors.muted },
  empty: { textAlign: 'center', marginTop: 40, color: colors.muted },
})
