import 'zmp-ui/zaui.min.css'
import './app.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createRoot } from 'react-dom/client'
import { App, SnackbarProvider } from 'zmp-ui'

import appConfig from '../app-config.json'
import { SessionProvider } from './lib/session'
import { Root } from './Root'

if (!window.APP_CONFIG) window.APP_CONFIG = appConfig

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1 } } })

createRoot(document.getElementById('app')!).render(
  <App>
    <SnackbarProvider>
      <QueryClientProvider client={queryClient}>
        <SessionProvider>
          <Root />
        </SessionProvider>
      </QueryClientProvider>
    </SnackbarProvider>
  </App>,
)
