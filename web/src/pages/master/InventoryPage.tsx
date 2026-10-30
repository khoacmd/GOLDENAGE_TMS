import type { components } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import { Card, Input, Select, Space, Table } from 'antd'
import { useState } from 'react'

import { api } from '../../api'
import { unwrap, usePaging } from '../../lib/api-helpers'
import { fmtDateTime, fmtNumber } from '../../lib/labels'

type Row = components['schemas']['InventoryOut']

export function InventoryPage() {
  const paging = usePaging(50)
  const [warehouseId, setWarehouseId] = useState<string>()
  const warehouses = useQuery({
    queryKey: ['warehouses', 'all'],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/warehouses', { params: { query: { limit: 500 } } })),
  })
  const query = useQuery({
    queryKey: ['inventory', paging.params, warehouseId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/inventory', {
          params: { query: { ...paging.params, warehouse_id: warehouseId } },
        }),
      ),
  })

  return (
    <Card
      title="Tồn kho"
      extra={
        <Space>
          <Select
            allowClear
            placeholder="Tất cả kho"
            style={{ width: 200 }}
            value={warehouseId}
            onChange={setWarehouseId}
            options={warehouses.data?.items.map((w) => ({ value: w.id, label: `${w.code} - ${w.name}` }))}
          />
          <Input.Search placeholder="Tìm mã, tên hàng" allowClear onSearch={paging.search} />
        </Space>
      }
    >
      <Table<Row>
        rowKey={(r) => `${r.warehouse_id}-${r.product_id}`}
        loading={query.isLoading}
        dataSource={query.data?.items}
        pagination={paging.pagination(query.data?.total)}
        scroll={{ x: 700 }}
        columns={[
          { title: 'Kho', dataIndex: 'warehouse_code', width: 100 },
          { title: 'Mã hàng', dataIndex: 'product_code', width: 150 },
          { title: 'Tên hàng', dataIndex: 'product_name' },
          { title: 'Tồn', dataIndex: 'qty_on_hand', width: 110, align: 'right', render: fmtNumber },
          { title: 'ĐVT', dataIndex: 'uom', width: 90 },
          { title: 'Đồng bộ lúc', dataIndex: 'synced_at', width: 170, render: fmtDateTime },
        ]}
      />
    </Card>
  )
}
