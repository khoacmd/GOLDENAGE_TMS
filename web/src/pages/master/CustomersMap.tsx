import { useQuery } from '@tanstack/react-query'
import { Alert, Space, Switch, Typography } from 'antd'
import { useMemo, useState } from 'react'

import { api } from '../../api'
import { unwrap } from '../../lib/api-helpers'
import { MapView, type MapPoint } from '../../lib/MapView'
import { useTrafficZones } from '../../lib/useTrafficZones'

const NO_MARKERS: never[] = []

/** Bản đồ mọi điểm giao đang hoạt động của các khách hàng khớp ô tìm kiếm (không theo trang). */
export function CustomersMap({ q, onEdit }: { q?: string; onEdit?: (customerId: string) => void }) {
  const [showZones, setShowZones] = useState(false)
  const zones = useTrafficZones()
  const query = useQuery({
    queryKey: ['customers', 'locations', q],
    queryFn: async () => unwrap(await api.GET('/api/v1/customers/locations', { params: { query: { q } } })),
  })
  const points = useMemo<MapPoint[]>(
    () =>
      (query.data?.items ?? []).map((p) => ({
        // Bấm vào điểm mở khách hàng của điểm đó.
        id: p.customer_id,
        lat: Number(p.latitude),
        lng: Number(p.longitude),
        title: `${p.customer_code} - ${p.customer_name} (${p.point_code})`,
        description: p.address,
        color: p.customer_active ? '#1677ff' : '#8c8c8c',
      })),
    [query.data],
  )
  const customers = new Set(query.data?.items.map((p) => p.customer_id)).size

  return (
    <Space orientation="vertical" style={{ width: '100%', marginBottom: 16 }}>
      <Space wrap>
        <Typography.Text type="secondary">
          {query.isLoading ? 'Đang tải…' : `${customers} khách hàng, ${points.length} điểm giao`}
        </Typography.Text>
        <Switch size="small" checked={showZones} onChange={setShowZones} />
        <Typography.Text>Vùng hạn chế lưu hành</Typography.Text>
      </Space>
      {query.data?.truncated && (
        <Alert type="warning" showIcon title="Quá nhiều điểm, bản đồ chỉ hiện một phần. Tìm theo mã/tên để thu hẹp." />
      )}
      <MapView
        markers={NO_MARKERS}
        points={points}
        zones={showZones ? zones : undefined}
        onPointAction={onEdit}
        height={360}
      />
    </Space>
  )
}
