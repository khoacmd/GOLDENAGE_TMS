import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { components } from '@tms/api-client'
import { useState } from 'react'
import { App, Button, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from 'antd'

import { api } from '../../api'
import { unwrap } from '../../lib/api-helpers'
import { useEntityModal } from '../../lib/crud'
import { fmtDate } from '../../lib/labels'

type Vehicle = components['schemas']['VehicleOut']
type Permit = components['schemas']['PermitOut']
type PermitBody = components['schemas']['PermitIn']
type PermitForm = Omit<PermitBody, 'windows'> & { windows: string }

const WINDOWS_RULE = {
  pattern: /^\s*\d{2}:\d{2}\s*-\s*\d{2}:\d{2}(\s*,\s*\d{2}:\d{2}\s*-\s*\d{2}:\d{2})*\s*$/,
  message: 'Nhập dạng 09:00-16:00, có thể nhiều khung cách nhau dấu phẩy',
}

const parseWindows = (text: string) =>
  text.split(',').map((w) => w.split('-').map((t) => t.trim()) as [string, string])

/** Văn bản chấp thuận cho xe hoạt động ngoài khung giờ trong vùng hạn chế. */
export function VehiclePermitsModal({
  vehicle,
  canEdit,
  onClose,
}: {
  vehicle: Vehicle | null
  canEdit: boolean
  onClose(): void
}) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const vehicleId = vehicle?.id ?? ''
  const query = useQuery({
    queryKey: ['vehicle-permits', vehicleId],
    enabled: Boolean(vehicle),
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/vehicles/{vehicle_id}/permits', { params: { path: { vehicle_id: vehicleId } } })),
  })
  const zones = useQuery({
    queryKey: ['traffic-zones'],
    enabled: Boolean(vehicle),
    queryFn: async () => unwrap(await api.GET('/api/v1/traffic/zones')),
  })
  const modal = useEntityModal<Permit, PermitForm>({
    queryKey: 'vehicle-permits',
    title: 'văn bản chấp thuận',
    toForm: (p) => ({ ...p, windows: p.windows.map((w) => w.join('-')).join(', ') }) as never,
    save: async (values, editing) => {
      const body: PermitBody = { ...values, windows: parseWindows(values.windows) }
      return editing
        ? unwrap(
            await api.PUT('/api/v1/vehicles/{vehicle_id}/permits/{permit_id}', {
              params: { path: { vehicle_id: vehicleId, permit_id: editing.id } },
              body,
            }),
          )
        : unwrap(
            await api.POST('/api/v1/vehicles/{vehicle_id}/permits', {
              params: { path: { vehicle_id: vehicleId } },
              body,
            }),
          )
    },
  })
  const remove = useMutation({
    mutationFn: async (permit: Permit) =>
      unwrap(
        await api.DELETE('/api/v1/vehicles/{vehicle_id}/permits/{permit_id}', {
          params: { path: { vehicle_id: vehicleId, permit_id: permit.id } },
        }),
      ),
    onSuccess: async () => {
      message.success('Đã xóa văn bản')
      await queryClient.invalidateQueries({ queryKey: ['vehicle-permits'] })
    },
    onError: (e: Error) => message.error(e.message),
  })
  const [today] = useState(() => new Date().toISOString().slice(0, 10))
  const zoneName = new Map(zones.data?.map((z) => [z.id, z.name]))

  return (
    <Modal
      open={Boolean(vehicle)}
      title={`Văn bản chấp thuận - ${vehicle?.code ?? ''}`}
      width={900}
      footer={null}
      onCancel={onClose}
      destroyOnHidden
    >
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Typography.Text type="secondary">
          Khung giờ trong văn bản được cộng thêm vào giờ theo quy định. Hệ thống không kiểm tra được tuyến đường ghi
          trong văn bản: lái xe vẫn phải đi đúng tuyến được cấp.
        </Typography.Text>
        {canEdit && (
          <Button type="primary" onClick={() => modal.show(null)}>
            Thêm văn bản
          </Button>
        )}
        <Table<Permit>
          rowKey="id"
          size="small"
          loading={query.isLoading}
          dataSource={query.data}
          pagination={false}
          columns={[
            { title: 'Số văn bản', dataIndex: 'document_no' },
            { title: 'Cơ quan cấp', dataIndex: 'issuer' },
            { title: 'Vùng', dataIndex: 'zone_id', render: (v: string) => zoneName.get(v) },
            {
              title: 'Khung giờ',
              dataIndex: 'windows',
              render: (v: Permit['windows']) => v.map((w) => w.join('-')).join(', '),
            },
            {
              title: 'Hiệu lực',
              render: (_, p) => (
                <>
                  {fmtDate(p.valid_from)} - {fmtDate(p.valid_to)}{' '}
                  {p.valid_to < today && <Tag color="red">Hết hạn</Tag>}
                </>
              ),
            },
            ...(canEdit
              ? [
                  {
                    title: '',
                    width: 90,
                    render: (_: unknown, p: Permit) => (
                      <Space>
                        <a onClick={() => modal.show(p)}>Sửa</a>
                        <Popconfirm title="Xóa văn bản này?" onConfirm={() => remove.mutate(p)}>
                          <a>Xóa</a>
                        </Popconfirm>
                      </Space>
                    ),
                  },
                ]
              : []),
          ]}
        />
      </Space>
      {modal.render(() => (
        <>
          <Form.Item name="zone_id" label="Vùng hạn chế" rules={[{ required: true }]}>
            <Select options={zones.data?.map((z) => ({ value: z.id, label: z.name }))} />
          </Form.Item>
          <Form.Item name="document_no" label="Số văn bản" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="issuer" label="Cơ quan cấp">
            <Input placeholder="vd. Công an TP Hà Nội" />
          </Form.Item>
          <Space size="middle">
            <Form.Item name="valid_from" label="Ngày hiệu lực" rules={[{ required: true }]}>
              <Input type="date" />
            </Form.Item>
            <Form.Item name="valid_to" label="Ngày hết hạn" rules={[{ required: true }]}>
              <Input type="date" />
            </Form.Item>
          </Space>
          <Form.Item name="windows" label="Khung giờ được phép" rules={[{ required: true }, WINDOWS_RULE]}>
            <Input placeholder="07:00-19:00" />
          </Form.Item>
          <Form.Item name="note" label="Ghi chú" extra="vd. tuyến đường được cấp, loại hàng">
            <Input />
          </Form.Item>
        </>
      ))}
    </Modal>
  )
}
