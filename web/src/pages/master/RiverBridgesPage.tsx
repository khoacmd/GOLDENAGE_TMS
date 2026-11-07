import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Form, Input, InputNumber, Popconfirm, Select, Space, Switch, Table, Tag } from 'antd'
import { useMemo } from 'react'

import { api } from '../../api'
import { useAuth } from '../../auth-context'
import { CODE_RULE, unwrap } from '../../lib/api-helpers'
import { CoordinateFields } from '../../lib/CoordinateFields'
import { mapLink, useEntityModal } from '../../lib/crud'
import { fmtNumber } from '../../lib/labels'
import { MapView, type MapMarker, type MapRoute } from '../../lib/MapView'

type Bridge = components['schemas']['BridgeOut']
type BridgeForm = components['schemas']['BridgeIn']

// Từ mức này coi là "hạn chế tối đa" (tô đỏ trên bảng và bản đồ).
const HIGH_PENALTY = 1_000_000

export function RiverBridgesPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const { hasRole } = useAuth()
  const canEdit = hasRole('company_admin')
  const rivers = useQuery({
    queryKey: ['rivers'],
    queryFn: async () => unwrap(await api.GET('/api/v1/rivers')),
  })
  const bridges = useQuery({
    queryKey: ['river-bridges'],
    queryFn: async () => unwrap(await api.GET('/api/v1/river-bridges')),
  })
  const riverName = (code: string) => rivers.data?.find((r) => r.code === code)?.name ?? code

  const modal = useEntityModal<Bridge, BridgeForm>({
    queryKey: 'river-bridges',
    title: 'cầu',
    defaults: { is_active: true, motorbike_penalty: 0, river_code: 'SONG_HONG' },
    save: async (values, editing) =>
      editing
        ? unwrap(
            await api.PUT('/api/v1/river-bridges/{bridge_id}', {
              params: { path: { bridge_id: editing.id } },
              body: values,
            }),
          )
        : unwrap(await api.POST('/api/v1/river-bridges', { body: values })),
  })

  const loadDefaults = useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/v1/river-bridges/load-defaults')),
    onSuccess: async (data) => {
      message.success(data.created ? `Đã thêm ${data.created} cầu mẫu` : 'Các cầu mẫu đã có đủ')
      await queryClient.invalidateQueries({ queryKey: ['river-bridges'] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const remove = useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.DELETE('/api/v1/river-bridges/{bridge_id}', { params: { path: { bridge_id: id } } })),
    onSuccess: async () => {
      message.success('Đã xóa cầu')
      await queryClient.invalidateQueries({ queryKey: ['river-bridges'] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  const routes = useMemo<MapRoute[]>(
    () =>
      (rivers.data ?? []).map((r) => ({
        id: r.code,
        color: '#1677ff',
        coords: r.path.map(([lat, lng]) => [lng, lat] as [number, number]),
      })),
    [rivers.data],
  )
  const markers = useMemo<MapMarker[]>(
    () =>
      (bridges.data ?? [])
        .filter((b) => b.is_active)
        .map((b) => ({
          id: b.id,
          lat: Number(b.latitude),
          lng: Number(b.longitude),
          label: b.name.replace(/^Cầu\s+/, ''),
          color: b.motorbike_penalty >= HIGH_PENALTY ? '#cf1322' : '#389e0d',
          title: `${b.name} - phạt xe máy ${fmtNumber(b.motorbike_penalty)} đ`,
        })),
    [bridges.data],
  )

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card
        title="Cầu vượt sông"
        extra={
          canEdit && (
            <Space wrap>
              <Button loading={loadDefaults.isPending} onClick={() => loadDefaults.mutate()}>
                Thêm cầu mẫu Hà Nội
              </Button>
              <Button type="primary" onClick={() => modal.show(null)}>
                Thêm cầu
              </Button>
            </Space>
          )
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          title="Tham số lập kế hoạch tự động cho xe máy"
          description={
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              <li>
                Mỗi lần xe máy đi qua sông (giữa 2 điểm ở 2 bờ), bộ tối ưu cộng thêm mức phạt của cây cầu dự kiến đi
                qua (cầu có phạt + quãng đường đi vòng nhỏ nhất). Mức phạt chỉ dùng để so sánh phương án, không tính
                vào chi phí chuyến.
              </li>
              <li>
                Nhờ đó xe máy ưu tiên giao các điểm cùng bờ sông với kho; điểm bên kia sông được giao cho ô tô hoặc đi
                qua cầu có mức phạt thấp. Cầu muốn tránh tối đa: đặt mức phạt lớn (từ {fmtNumber(HIGH_PENALTY)} đ).
              </li>
              <li>Sông chưa có cầu nào đang dùng thì không xét. Ô tô không bị ảnh hưởng.</li>
            </ul>
          }
        />
        <Table<Bridge>
          rowKey="id"
          size="small"
          loading={bridges.isLoading}
          dataSource={bridges.data}
          pagination={false}
          scroll={{ x: 900 }}
          onRow={(r) => ({ onDoubleClick: () => canEdit && modal.show(r) })}
          columns={[
            { title: 'Sông', dataIndex: 'river_code', width: 110, render: riverName },
            { title: 'Mã', dataIndex: 'code', width: 130 },
            { title: 'Tên cầu', dataIndex: 'name' },
            {
              title: 'Tọa độ',
              width: 180,
              render: (_, r) => (
                <a href={mapLink(r.latitude, r.longitude)} target="_blank" rel="noreferrer">
                  {Number(r.latitude).toFixed(5)}, {Number(r.longitude).toFixed(5)}
                </a>
              ),
            },
            {
              title: 'Phạt xe máy (đ)',
              dataIndex: 'motorbike_penalty',
              width: 140,
              align: 'right',
              render: (v: number) =>
                v >= HIGH_PENALTY ? <Tag color="red">{fmtNumber(v)}</Tag> : fmtNumber(v),
            },
            { title: 'Ghi chú', dataIndex: 'note' },
            {
              title: 'Trạng thái',
              dataIndex: 'is_active',
              width: 110,
              render: (v: boolean) => (v ? <Tag color="green">Đang dùng</Tag> : <Tag>Ngưng</Tag>),
            },
            ...(canEdit
              ? [
                  {
                    title: '',
                    width: 100,
                    render: (_: unknown, r: Bridge) => (
                      <Space>
                        <a onClick={() => modal.show(r)}>Sửa</a>
                        <Popconfirm title={`Xóa ${r.name}?`} onConfirm={() => remove.mutate(r.id)}>
                          <a>Xóa</a>
                        </Popconfirm>
                      </Space>
                    ),
                  },
                ]
              : []),
          ]}
        />
      </Card>
      <Card title="Bản đồ sông và cầu" size="small">
        <MapView markers={markers} routes={routes} height="min(520px, 60vh)" />
      </Card>
      {modal.render((_, editing) => (
        <>
          <Form.Item name="river_code" label="Sông" rules={[{ required: true }]}>
            <Select options={rivers.data?.map((r) => ({ value: r.code, label: r.name }))} />
          </Form.Item>
          <Form.Item name="code" label="Mã cầu" rules={[{ required: true }, CODE_RULE]}>
            <Input disabled={Boolean(editing)} />
          </Form.Item>
          <Form.Item name="name" label="Tên cầu" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <CoordinateFields />
          <Form.Item
            name="motorbike_penalty"
            label="Phạt xe máy qua cầu (đ)"
            rules={[{ required: true }]}
            extra={`0 = không hạn chế; càng lớn càng tránh (vd. ${fmtNumber(HIGH_PENALTY)} đ = hạn chế tối đa).`}
          >
            <InputNumber min={0} step={50000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="note" label="Ghi chú">
            <Input />
          </Form.Item>
          <Form.Item name="is_active" label="Đang dùng" valuePropName="checked">
            <Switch />
          </Form.Item>
        </>
      ))}
    </Space>
  )
}
