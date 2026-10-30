import NetInfo from '@react-native-community/netinfo'
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { StatusBar } from 'expo-status-bar'
import { useEffect, useState } from 'react'
import { ActivityIndicator, AppState, BackHandler, View } from 'react-native'

import { api, loadStoredTokens, tokenStore } from './src/api'
import { processQueue } from './src/queue'
import { ConfirmScreen } from './src/screens/ConfirmScreen'
import { LoginScreen } from './src/screens/LoginScreen'
import { TripListScreen } from './src/screens/TripListScreen'
import { TripScreen, type Item, type Stop, type Trip } from './src/screens/TripScreen'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1 } } })

type Route = { name: 'list' } | { name: 'trip'; tripId: string } | { name: 'confirm'; trip: Trip; stop: Stop; item: Item }

/** Gửi hàng đợi xác nhận khi có mạng trở lại, khi mở lại app và định kỳ mỗi 30 giây. */
function useQueueSync() {
  const client = useQueryClient()
  useEffect(() => {
    const sync = () => void processQueue().then(() => client.invalidateQueries({ queryKey: ['driver-trip'] }))
    const net = NetInfo.addEventListener((s) => s.isConnected && sync())
    const app = AppState.addEventListener('change', (s) => s === 'active' && sync())
    const timer = setInterval(sync, 30_000)
    return () => {
      net()
      app.remove()
      clearInterval(timer)
    }
  }, [client])
}

function Root() {
  const client = useQueryClient()
  const [stack, setStack] = useState<Route[]>([{ name: 'list' }])
  const route = stack[stack.length - 1]
  const push = (r: Route) => setStack((s) => [...s, r])
  const back = () => setStack((s) => (s.length > 1 ? s.slice(0, -1) : s))
  useQueueSync()

  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (stack.length <= 1) return false
      back()
      return true
    })
    return () => sub.remove()
  }, [stack.length])

  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      if (!tokenStore.get()) await loadStoredTokens()
      if (!tokenStore.get()) return null
      const { data, response } = await api.GET('/api/v1/auth/me')
      if (response.status === 401) tokenStore.set(null)
      return data ?? null
    },
    staleTime: Infinity,
  })
  const refreshMe = () => void client.invalidateQueries({ queryKey: ['me'] })

  if (meQuery.isLoading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center' }}>
        <ActivityIndicator size="large" />
      </View>
    )
  }
  if (!meQuery.data) return <LoginScreen onLoggedIn={refreshMe} />

  if (route.name === 'trip')
    return <TripScreen tripId={route.tripId} onBack={back} onConfirm={(trip, stop, item) => push({ name: 'confirm', trip, stop, item })} />
  if (route.name === 'confirm') return <ConfirmScreen trip={route.trip} stop={route.stop} item={route.item} onDone={back} />
  return (
    <TripListScreen
      me={meQuery.data}
      onOpen={(tripId) => push({ name: 'trip', tripId })}
      onLogout={() => {
        tokenStore.set(null)
        client.clear()
        refreshMe()
      }}
    />
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Root />
      <StatusBar style="dark" />
    </QueryClientProvider>
  )
}
