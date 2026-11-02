import { Box, Page, Text } from 'zmp-ui'

import { useSession, type Account } from '../lib/useSession'

const KIND: Record<Account['kind'], string> = { customer: 'Khách hàng', driver: 'Tài xế' }

export function ChooseAccountPage({ accounts }: { accounts: Account[] }) {
  const { choose, setActivating } = useSession()
  return (
    <Page className="screen">
      <Box p={4}>
        <Text.Title size="large">Chọn tài khoản</Text.Title>
        <Text className="muted">Zalo của bạn liên kết với nhiều tài khoản.</Text>
      </Box>
      {accounts.map((account) => (
        <button
          key={`${account.company.id}-${account.kind}`}
          className="card row-button"
          onClick={() => choose(account)}
        >
          <Text bold>{account.company.name}</Text>
          <Text className="muted">{KIND[account.kind]}</Text>
        </button>
      ))}
      <button className="link-button" onClick={() => setActivating(true)}>
        Nhập mã kích hoạt khác
      </button>
    </Page>
  )
}
