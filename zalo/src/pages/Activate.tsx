import { useState } from 'react'
import { Box, Button, Input, Page, Text } from 'zmp-ui'

import { useSession } from '../lib/useSession'

/** Nhập mã kích hoạt do công ty cấp (có sẵn nếu mở từ link/QR). */
export function ActivatePage({ onCancel }: { onCancel?: () => void }) {
  const { activate, initialCode } = useSession()
  const [code, setCode] = useState(initialCode ?? '')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit() {
    setSubmitting(true)
    setError(null)
    setError(await activate(code.trim()))
    setSubmitting(false)
  }

  return (
    <Page className="screen">
      <Box p={4} className="card">
        <Text.Title size="large">Kích hoạt tài khoản</Text.Title>
        <Text className="muted">
          Nhập mã kích hoạt do công ty giao hàng cung cấp để xem đơn hàng của bạn. Mỗi mã chỉ dùng một lần.
        </Text>
        <Box mt={4}>
          <Input
            label="Mã kích hoạt"
            placeholder="XXXX-XXXX"
            value={code}
            maxLength={16}
            status={error ? 'error' : undefined}
            errorText={error ?? undefined}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
          />
        </Box>
        <Box mt={4}>
          <Button fullWidth loading={submitting} disabled={!code.trim()} onClick={() => void submit()}>
            Kích hoạt
          </Button>
        </Box>
        {onCancel && (
          <Box mt={2}>
            <Button fullWidth variant="tertiary" onClick={onCancel}>
              Để sau
            </Button>
          </Box>
        )}
      </Box>
    </Page>
  )
}
