import { errorMessage } from '@tms/api-client'
import { useState } from 'react'
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native'

import { api, API_URL, tokenStore } from '../api'

export function LoginScreen({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [companyCode, setCompanyCode] = useState('')
  const [needCompany, setNeedCompany] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit() {
    setSubmitting(true)
    setError(null)
    try {
      const { data, error: err } = await api.POST('/api/v1/auth/login', {
        body: { username, password, company_code: companyCode || null },
      })
      if (data) {
        tokenStore.set(data)
        onLoggedIn()
        return
      }
      const body = err as { error?: { code?: string } } | undefined
      if (body?.error?.code === 'company_required') setNeedCompany(true)
      setError(errorMessage(err, 'Đăng nhập thất bại'))
    } catch (e) {
      console.warn('Đăng nhập lỗi', e)
      setError(`Không kết nối được máy chủ (${API_URL})`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>TMS Giao hàng</Text>
      {error && <Text style={styles.error}>{error}</Text>}
      <TextInput
        style={styles.input}
        placeholder="Tên đăng nhập"
        autoCapitalize="none"
        value={username}
        onChangeText={setUsername}
      />
      <TextInput
        style={styles.input}
        placeholder="Mật khẩu"
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />
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
        style={[styles.button, submitting && styles.buttonDisabled]}
        onPress={submit}
        disabled={submitting || !username || !password}
      >
        {submitting ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.buttonText}>Đăng nhập</Text>
        )}
      </Pressable>
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 24, gap: 12, backgroundColor: '#fff' },
  title: { fontSize: 24, fontWeight: '600', textAlign: 'center', marginBottom: 12 },
  error: { color: '#c62828', textAlign: 'center' },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 8, padding: 12, fontSize: 16 },
  button: { backgroundColor: '#1677ff', borderRadius: 8, padding: 14, alignItems: 'center' },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '600' },
})
