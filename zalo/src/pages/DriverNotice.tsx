import { Box, Button, Page, Text } from 'zmp-ui'

import { useSession } from '../lib/useSession'

/** Phần tài xế trên Zalo làm ở bước sau; tài xế dùng ứng dụng TMS (kênh chính). */
export function DriverNoticePage() {
  const { switchAccount } = useSession()
  return (
    <Page className="screen">
      <Box p={4} className="card">
        <Text.Title>Tài khoản tài xế</Text.Title>
        <Text className="muted">
          Chức năng cho tài xế trên Zalo sắp ra mắt. Vui lòng dùng ứng dụng TMS để nhận chuyến và xác nhận giao hàng.
        </Text>
        <Box mt={4}>
          <Button fullWidth variant="secondary" onClick={switchAccount}>
            Đổi tài khoản
          </Button>
        </Box>
      </Box>
    </Page>
  )
}
