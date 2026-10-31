import { errorMessage } from '@tms/api-client'
import * as SecureStore from 'expo-secure-store'
import { useEffect, useState } from 'react'
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native'

import { api, API_URL, tokenStore } from '../api'

type Mode = 'password' | 'pin'
const PIN_LENGTH = 6
// Nhớ tên đăng nhập + cách đăng nhập lần trước: lái xe dùng PIN chỉ cần gõ 6 số.
const LAST_LOGIN_KEY = 'tms.last_login'

export function LoginScreen({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [mode, setMode] = useState<Mode>('password')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [pin, setPin] = useState('')
  const [companyCode, setCompanyCode] = useState('')
  const [needCompany, setNeedCompany] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    void SecureStore.getItemAsync(LAST_LOGIN_KEY).then((raw) => {
      if (!raw) return
      const last = JSON.parse(raw) as { username: string; mode: Mode }
      setUsername(last.username)
      setMode(last.mode)
    })
  }, [])

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
    setPassword('')
    setPin('')
  }

  async function submit(pinValue = pin) {
    setSubmitting(true)
    setError(null)
    try {
      const company_code = companyCode || null
      const { data, error: err } =
        mode === 'pin'
          ? await api.POST('/api/v1/auth/login-pin', { body: { username, pin: pinValue, company_code } })
          : await api.POST('/api/v1/auth/login', { body: { username, password, company_code } })
      if (data) {
        await SecureStore.setItemAsync(LAST_LOGIN_KEY, JSON.stringify({ username, mode }))
        tokenStore.set(data)
        onLoggedIn()
        return
      }
      const body = err as { error?: { code?: string } } | undefined
      if (body?.error?.code === 'company_required') setNeedCompany(true)
      setPin('')
      setError(errorMessage(err, 'Đăng nhập thất bại'))
    } catch (e) {
      console.warn('Đăng nhập lỗi', e)
      setError(`Không kết nối được máy chủ (${API_URL})`)
    } finally {
      setSubmitting(false)
    }
  }

  function changePin(text: string) {
    const digits = text.replace(/\D/g, '').slice(0, PIN_LENGTH)
    setPin(digits)
    // Đủ 6 số thì tự đăng nhập (trừ khi còn thiếu mã công ty).
    if (digits.length === PIN_LENGTH && username && !submitting && (!needCompany || companyCode)) void submit(digits)
  }

  const ready = Boolean(username) && (mode === 'pin' ? pin.length === PIN_LENGTH : Boolean(password))

  return (
    <View style={styles.container}>
      <Text style={styles.title}>TMS Giao hàng</Text>
      <View style={styles.tabs}>
        {(['password', 'pin'] as const).map((m) => (
          <Pressable key={m} style={[styles.tab, mode === m && styles.tabActive]} onPress={() => switchMode(m)}>
            <Text style={[styles.tabText, mode === m && styles.tabTextActive]}>{m === 'pin' ? 'Mã PIN' : 'Mật khẩu'}</Text>
          </Pressable>
        ))}
      </View>
      {error && <Text style={styles.error}>{error}</Text>}
      <TextInput
        style={styles.input}
        placeholder="Tên đăng nhập"
        autoCapitalize="none"
        value={username}
        onChangeText={setUsername}
      />
      {mode === 'pin' ? (
        <TextInput
          style={[styles.input, pin ? styles.pin : styles.pinEmpty]}
          placeholder="Mã PIN 6 số"
          keyboardType="number-pad"
          secureTextEntry
          maxLength={PIN_LENGTH}
          value={pin}
          onChangeText={changePin}
        />
      ) : (
        <TextInput
          style={styles.input}
          placeholder="Mật khẩu"
          secureTextEntry
          value={password}
          onChangeText={setPassword}
        />
      )}
      {needCompany && (
        <TextInput
          style={styles.input}
          placeholder="Mã công ty"
          autoCapitalize="characters"
          value={companyCode}
          onChangeText={setCompanyCode}
        />
      )}
      <Pressable
        style={[styles.button, (submitting || !ready) && styles.buttonDisabled]}
        onPress={() => void submit()}
        disabled={submitting || !ready}
      >
        {submitting ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.buttonText}>Đăng nhập</Text>
        )}
      </Pressable>
      {mode === 'pin' && <Text style={styles.hint}>Mã PIN do quản trị công ty cấp, chỉ dùng cho tài khoản lái xe.</Text>}
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 24, gap: 12, backgroundColor: '#fff' },
  title: { fontSize: 24, fontWeight: '600', textAlign: 'center', marginBottom: 12 },
  tabs: { flexDirection: 'row', borderWidth: 1, borderColor: '#1677ff', borderRadius: 8, overflow: 'hidden' },
  tab: { flex: 1, padding: 10, alignItems: 'center' },
  tabActive: { backgroundColor: '#1677ff' },
  tabText: { color: '#1677ff', fontWeight: '600' },
  tabTextActive: { color: '#fff' },
  error: { color: '#c62828', textAlign: 'center' },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 8, padding: 12, fontSize: 16 },
  pin: { fontSize: 22, letterSpacing: 8, textAlign: 'center' },
  pinEmpty: { textAlign: 'center' },
  button: { backgroundColor: '#1677ff', borderRadius: 8, padding: 14, alignItems: 'center' },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  hint: { color: '#8c8c8c', textAlign: 'center', fontSize: 13 },
})
