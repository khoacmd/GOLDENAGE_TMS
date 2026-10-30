import { useQuery } from '@tanstack/react-query'
import * as ImagePicker from 'expo-image-picker'
import * as Location from 'expo-location'
import { useState } from 'react'
import { Alert, Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native'

import { api } from '../api'
import { TEMP_GROUP, fmtNumber } from '../lib/format'
import { Button, Card, Header, colors } from '../lib/ui'
import { enqueue } from '../queue'
import type { Item, Stop, Trip } from './TripScreen'

const REASONS = ['Khách vắng nhà / đóng cửa', 'Khách từ chối nhận', 'Sai hàng / thiếu hàng', 'Không liên lạc được khách']

async function currentPosition() {
  const perm = await Location.requestForegroundPermissionsAsync()
  if (perm.status !== 'granted') return null
  try {
    return await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High })
  } catch (e) {
    console.warn('Không lấy được vị trí hiện tại', e)
    return Location.getLastKnownPositionAsync().catch(() => null)
  }
}

export function ConfirmScreen({ trip, stop, item, onDone }: { trip: Trip; stop: Stop; item: Item; onDone: () => void }) {
  const [status, setStatus] = useState<'SUCCESS' | 'FAILED'>('SUCCESS')
  const [reason, setReason] = useState('')
  const [photos, setPhotos] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const rules = useQuery({
    queryKey: ['driver-rules'],
    queryFn: async () => (await api.GET('/api/v1/driver/rules')).data ?? null,
    staleTime: 10 * 60_000,
  })
  const photoRequired = rules.data ? (status === 'SUCCESS' ? rules.data.photo_required_success : rules.data.photo_required_failed) : false

  async function takePhoto(fromLibrary = false) {
    const perm = fromLibrary ? await ImagePicker.requestMediaLibraryPermissionsAsync() : await ImagePicker.requestCameraPermissionsAsync()
    if (!perm.granted) return Alert.alert('Cần quyền', fromLibrary ? 'Cho phép truy cập ảnh.' : 'Cho phép dùng camera để chụp chứng từ.')
    const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.5 }
    const result = fromLibrary ? await ImagePicker.launchImageLibraryAsync(options) : await ImagePicker.launchCameraAsync(options)
    if (!result.canceled) setPhotos((p) => [...p, result.assets[0].uri].slice(0, 5))
  }

  async function submit() {
    if (status === 'FAILED' && !reason.trim()) return Alert.alert('Thiếu lý do', 'Chọn hoặc nhập lý do giao không thành công.')
    if (photoRequired && photos.length === 0) return Alert.alert('Thiếu ảnh', 'Cần chụp ảnh chứng từ giao nhận.')
    setSaving(true)
    try {
      const pos = await currentPosition()
      enqueue({
        tripId: trip.id,
        itemId: item.id,
        label: item.external_ref ?? item.description ?? '',
        body: {
          status,
          reason: status === 'FAILED' ? reason.trim() : null,
          device_time: new Date().toISOString(),
          latitude: pos?.coords.latitude ?? null,
          longitude: pos?.coords.longitude ?? null,
          accuracy_m: pos?.coords.accuracy ?? null,
          is_mock_location: pos?.mocked ?? false,
        },
        photoUris: photos,
      })
      onDone()
    } finally {
      setSaving(false)
    }
  }

  return (
    <View style={styles.screen}>
      <Header title="Xác nhận giao hàng" onBack={onDone} />
      <ScrollView contentContainerStyle={{ paddingBottom: 32 }}>
        <Card>
          <Text style={styles.bold}>{stop.customer_code ? `${stop.customer_code} - ${stop.customer_name}` : stop.name}</Text>
          <Text style={styles.muted}>{stop.address}</Text>
          <Text>
            {item.external_ref ? `Đơn ${item.external_ref} · ${TEMP_GROUP[item.temp_group ?? 'DRY']}` : item.description} ·{' '}
            {fmtNumber(item.weight_kg)} kg
          </Text>
        </Card>
        <Card>
          <Text style={styles.label}>Kết quả</Text>
          <View style={styles.row}>
            <Button title="Giao thành công" kind={status === 'SUCCESS' ? 'success' : 'outline'} onPress={() => setStatus('SUCCESS')} style={{ flex: 1 }} />
            <Button title="Không thành công" kind={status === 'FAILED' ? 'danger' : 'outline'} onPress={() => setStatus('FAILED')} style={{ flex: 1 }} />
          </View>
          {status === 'FAILED' && (
            <>
              {REASONS.map((r) => (
                <Pressable key={r} onPress={() => setReason(r)} style={[styles.reason, reason === r && styles.reasonActive]}>
                  <Text>{r}</Text>
                </Pressable>
              ))}
              <TextInput style={styles.input} placeholder="Lý do khác…" value={reason} onChangeText={setReason} multiline />
            </>
          )}
        </Card>
        <Card>
          <Text style={styles.label}>Ảnh chứng từ giao nhận {photoRequired ? '(bắt buộc)' : '(không bắt buộc)'}</Text>
          <View style={[styles.row, { flexWrap: 'wrap' }]}>
            {photos.map((uri) => (
              <Pressable key={uri} onLongPress={() => setPhotos((p) => p.filter((x) => x !== uri))}>
                <Image source={{ uri }} style={styles.photo} />
              </Pressable>
            ))}
          </View>
          <Button kind="outline" title="Chụp ảnh" onPress={() => void takePhoto()} />
          {__DEV__ && <Button kind="outline" title="Chọn ảnh có sẵn (chỉ bản dev)" onPress={() => void takePhoto(true)} />}
          {photos.length > 0 && <Text style={styles.muted}>Nhấn giữ ảnh để xóa.</Text>}
        </Card>
        {rules.data?.confirm_geofence && (
          <Text style={[styles.muted, { marginHorizontal: 16, marginTop: 8 }]}>
            Vị trí điện thoại sẽ được ghi nhận; cần ở trong bán kính {rules.data.confirm_radius_m} m quanh điểm giao.
          </Text>
        )}
        <Button title="Gửi xác nhận" loading={saving} onPress={() => void submit()} style={{ margin: 12 }} />
      </ScrollView>
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#f2f3f5' },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  bold: { fontSize: 16, fontWeight: '700' },
  label: { fontWeight: '600' },
  muted: { color: colors.muted },
  reason: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10 },
  reasonActive: { borderColor: colors.danger, backgroundColor: '#fff1f0' },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10, minHeight: 44 },
  photo: { width: 80, height: 80, borderRadius: 6 },
})
