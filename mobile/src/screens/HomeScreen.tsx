import type { Me } from '@tms/api-client'
import { Pressable, StyleSheet, Text, View } from 'react-native'

export function HomeScreen({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const isDriver = me.roles.includes('driver')
  return (
    <View style={styles.container}>
      <Text style={styles.title}>Xin chào, {me.full_name}</Text>
      <Text>{me.company?.name ?? 'Chưa thuộc công ty nào'}</Text>
      <Text style={styles.note}>
        {isDriver
          ? 'Danh sách chuyến giao được gán sẽ hiển thị ở đây (M3).'
          : 'Ứng dụng mobile dành cho nhân viên giao hàng.'}
      </Text>
      <Pressable style={styles.button} onPress={onLogout}>
        <Text style={styles.buttonText}>Đăng xuất</Text>
      </Pressable>
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 24, paddingTop: 64, gap: 12, backgroundColor: '#fff' },
  title: { fontSize: 22, fontWeight: '600' },
  note: { color: '#666', marginVertical: 12 },
  button: { borderWidth: 1, borderColor: '#1677ff', borderRadius: 8, padding: 12, alignItems: 'center' },
  buttonText: { color: '#1677ff', fontWeight: '600' },
})
