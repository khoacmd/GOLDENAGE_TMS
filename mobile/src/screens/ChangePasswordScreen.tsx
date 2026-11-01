import { errorMessage } from '@tms/api-client'
import { useState } from 'react'
import { Alert, StyleSheet, Text, TextInput, View } from 'react-native'

import { api, API_URL, tokenStore } from '../api'
import { Button, Card, Header, colors } from '../lib/ui'

const MIN_LENGTH = 8

/** Tự đổi mật khẩu; phiên hiện tại nhận token mới, các máy khác bị đăng xuất. */
export function ChangePasswordScreen({ onBack }: { onBack: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit() {
    if (next.length < MIN_LENGTH) return setError(`Mật khẩu mới tối thiểu ${MIN_LENGTH} ký tự`)
    if (next !== confirm) return setError('Mật khẩu nhập lại không khớp')
    setSubmitting(true)
    setError(null)
    try {
      const { data, error: err } = await api.POST('/api/v1/auth/change-password', {
        body: { current_password: current, new_password: next },
      })
      if (!data) return setError(errorMessage(err, 'Đổi mật khẩu thất bại'))
      tokenStore.set(data)
      Alert.alert('Đã đổi mật khẩu', 'Các máy khác đang đăng nhập tài khoản này đã bị đăng xuất.')
      onBack()
    } catch (e) {
      console.warn('Đổi mật khẩu lỗi', e)
      setError(`Không kết nối được máy chủ (${API_URL})`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <View style={styles.screen}>
      <Header title="Đổi mật khẩu" onBack={onBack} />
      <Card>
        {error && <Text style={styles.error}>{error}</Text>}
        <TextInput style={styles.input} placeholder="Mật khẩu hiện tại" secureTextEntry value={current} onChangeText={setCurrent} />
        <TextInput style={styles.input} placeholder="Mật khẩu mới" secureTextEntry value={next} onChangeText={setNext} />
        <TextInput style={styles.input} placeholder="Nhập lại mật khẩu mới" secureTextEntry value={confirm} onChangeText={setConfirm} />
        <Button title="Đổi mật khẩu" onPress={() => void submit()} loading={submitting} disabled={!current || !next || !confirm} />
        <Text style={styles.hint}>Mã PIN đăng nhập (nếu có) không thay đổi.</Text>
      </Card>
    </View>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#f2f3f5' },
  error: { color: colors.danger },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 8, padding: 12, fontSize: 16 },
  hint: { color: colors.muted, fontSize: 13 },
})
