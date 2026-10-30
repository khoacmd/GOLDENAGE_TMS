import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { StatusBar } from 'expo-status-bar'
import { ActivityIndicator, View } from 'react-native'

import { api, loadStoredTokens, tokenStore } from './src/api'
import { HomeScreen } from './src/screens/HomeScreen'
import { LoginScreen } from './src/screens/LoginScreen'

const queryClient = new QueryClient()

function Root() {
  const client = useQueryClient()
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
  return (
    <HomeScreen
      me={meQuery.data}
      onLogout={() => {
        tokenStore.set(null)
        refreshMe()
      }}
    />
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Root />
      <StatusBar style="auto" />
    </QueryClientProvider>
  )
}
