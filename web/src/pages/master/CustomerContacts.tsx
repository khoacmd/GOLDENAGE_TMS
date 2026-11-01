import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { components } from '@tms/api-client'
import { App, Button, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography } from 'antd'

import { api } from '../../api'
import { unwrap } from '../../lib/api-helpers'
import { useEntityModal } from '../../lib/crud'
import { useZaloActivation } from '../../lib/useZaloActivation'
import { ZaloStatusTag } from '../../lib/zalo'

type Customer = components['schemas']['CustomerOut']
type Contact = components['schemas']['CustomerContactOut']
type ContactForm = components['schemas']['CustomerContactIn']

/** Người liên hệ dùng Zalo Mini App: liên hệ chủ (mọi đơn + giá trị) hoặc của 1 điểm giao. */
export function CustomerContactsModal({
  customer,
  canEdit,
  canIssueCodes,
  onClose,
}: {
  customer: Customer | null
  canEdit: boolean
  /** Cấp / thu hồi mã kích hoạt Zalo: chỉ admin công ty. */
  canIssueCodes: boolean
  onClose(): void
}) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const customerId = customer?.id ?? ''
  const query = useQuery({
    queryKey: ['customer-contacts', customerId],
    enabled: Boolean(customer),
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/customers/{customer_id}/contacts', {
          params: { path: { customer_id: customerId } },
        }),
      ),
  })

  const modal = useEntityModal<Contact, ContactForm>({
    queryKey: 'customer-contacts',
    title: 'liên hệ',
    defaults: { is_active: true },
    save: async (values, editing) =>
      editing
        ? unwrap(
            await api.PUT('/api/v1/customers/{customer_id}/contacts/{contact_id}', {
              params: { path: { customer_id: customerId, contact_id: editing.id } },
              body: values,
            }),
          )
        : unwrap(
            await api.POST('/api/v1/customers/{customer_id}/contacts', {
              params: { path: { customer_id: customerId } },
              body: values,
            }),
          ),
  })

  const zalo = useZaloActivation({
    queryKey: 'customer-contacts',
    issue: async (id) =>
      unwrap(
        await api.POST('/api/v1/customers/{customer_id}/contacts/{contact_id}/activation-code', {
          params: { path: { customer_id: customerId, contact_id: id } },
        }),
      ),
    revoke: async (id) =>
      unwrap(
        await api.DELETE('/api/v1/customers/{customer_id}/contacts/{contact_id}/zalo', {
          params: { path: { customer_id: customerId, contact_id: id } },
        }),
      ),
  })

  const remove = useMutation({
    mutationFn: async (contact: Contact) =>
      unwrap(
        await api.DELETE('/api/v1/customers/{customer_id}/contacts/{contact_id}', {
          params: { path: { customer_id: customerId, contact_id: contact.id } },
        }),
      ),
    onSuccess: async () => {
      message.success('Đã xóa liên hệ')
      await queryClient.invalidateQueries({ queryKey: ['customer-contacts'] })
    },
    onError: (e: Error) => message.error(e.message),
  })

  // Để trống = liên hệ chủ (antd Select không nhận option có value null).
  const pointOptions = (customer?.delivery_points ?? [])
    .filter((p) => p.is_active)
    .map((p) => ({ value: p.id, label: `Điểm giao ${p.code}${p.name ? ` - ${p.name}` : ''}` }))

  return (
    <Modal
      open={Boolean(customer)}
      title={`Liên hệ - ${customer?.code ?? ''} ${customer?.name ?? ''}`}
      width={1000}
      footer={null}
      onCancel={onClose}
      destroyOnHidden
    >
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Typography.Text type="secondary">
          Người dùng Zalo Mini App. Liên hệ chủ xem mọi đơn kèm giá trị; liên hệ điểm giao chỉ xem đơn đến
          điểm đó (mặt hàng, số lượng).
        </Typography.Text>
        {canEdit && (
          <Button type="primary" onClick={() => modal.show(null)}>
            Thêm liên hệ
          </Button>
        )}
        <Table<Contact>
          rowKey="id"
          size="small"
          loading={query.isLoading}
          dataSource={query.data}
          pagination={false}
          columns={[
            { title: 'Tên', dataIndex: 'name' },
            { title: 'Điện thoại', dataIndex: 'phone', width: 120 },
            {
              title: 'Phạm vi',
              width: 150,
              render: (_, c) =>
                c.delivery_point_code ? <Tag>Điểm giao {c.delivery_point_code}</Tag> : <Tag color="blue">Chủ</Tag>,
            },
            { title: 'Ghi chú', dataIndex: 'note' },
            {
              title: 'Zalo',
              width: 210,
              render: (_, c) => (
                <Space orientation="vertical" size={2}>
                  <ZaloStatusTag info={c.zalo} />
                  {canIssueCodes && c.is_active && zalo.actions(c.id, c.name, c.zalo)}
                </Space>
              ),
            },
            {
              title: 'Trạng thái',
              dataIndex: 'is_active',
              width: 100,
              render: (v: boolean) => (v ? <Tag color="green">Hoạt động</Tag> : <Tag>Ngưng</Tag>),
            },
            ...(canEdit
              ? [
                  {
                    title: '',
                    width: 90,
                    render: (_: unknown, c: Contact) => (
                      <Space>
                        <a onClick={() => modal.show(c)}>Sửa</a>
                        <Popconfirm title="Xóa liên hệ này?" onConfirm={() => remove.mutate(c)}>
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
      {zalo.modal}
      {modal.render(() => (
        <>
          <Form.Item name="name" label="Tên liên hệ" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="Điện thoại (Zalo)" rules={[{ required: true }]}>
            <Input placeholder="0912 345 678" />
          </Form.Item>
          <Form.Item name="delivery_point_id" label="Phạm vi xem đơn">
            <Select allowClear placeholder="Chủ khách hàng (xem mọi đơn + giá trị)" options={pointOptions} />
          </Form.Item>
          <Form.Item name="note" label="Ghi chú">
            <Input placeholder="vd. Thủ kho đại lý" />
          </Form.Item>
          <Form.Item name="is_active" label="Hoạt động" valuePropName="checked">
            <Switch />
          </Form.Item>
        </>
      ))}
    </Modal>
  )
}
