import { AnimationRoutes, Box, Button, Route, Spinner, Text, ZMPRouter } from 'zmp-ui'

import { useSession } from './lib/useSession'
import { ActivatePage } from './pages/Activate'
import { ChooseAccountPage } from './pages/ChooseAccount'
import { DriverNoticePage } from './pages/DriverNotice'
import { OrderDetailPage } from './pages/OrderDetail'
import { OrdersPage } from './pages/Orders'

function Screens() {
  const { state, activating, setActivating, retry } = useSession()
  if (state.status === 'loading') {
    return (
      <Box className="center">
        <Spinner />
      </Box>
    )
  }
  if (state.status === 'error') {
    return (
      <Box className="center">
        <Text>{state.message}</Text>
        <Box mt={4}>
          <Button onClick={retry}>Thử lại</Button>
        </Box>
      </Box>
    )
  }
  if (state.status === 'not_linked') return <ActivatePage />
  if (activating) return <ActivatePage onCancel={() => setActivating(false)} />
  if (state.status === 'choose') return <ChooseAccountPage accounts={state.accounts} />
  if (state.account.kind === 'driver') return <DriverNoticePage />
  return (
    <AnimationRoutes>
      <Route path="/" element={<OrdersPage />} />
      <Route path="/orders/:id" element={<OrderDetailPage />} />
    </AnimationRoutes>
  )
}

/** `Page` của zmp-ui cần nằm trong router, kể cả các màn hình trước khi đăng nhập xong. */
export function Root() {
  return (
    <ZMPRouter>
      <Screens />
    </ZMPRouter>
  )
}
