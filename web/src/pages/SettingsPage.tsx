import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  TimePicker,
  Typography,
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useState } from 'react'

import { api } from '../api'
import { unwrap } from '../lib/api-helpers'
import { WEEKDAYS, fmtDateTime } from '../lib/labels'

type ApiKey = components['schemas']['ApiKeyOut']

interface SettingsForm {
  working_weekdays: number[]
  shift: [Dayjs, Dayjs]
  cutover_time: Dayjs
  timezone: string
}

const T = 'HH:mm'

export function SettingsPage() {
  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <ShiftSettings />
      <ApiKeys />
    </Space>
  )
}

function ShiftSettings() {
  const { message } = App.useApp()
  const [form] = Form.useForm<SettingsForm>()
  const query = useQuery({
    queryKey: ['company-settings'],
    queryFn: async () => unwrap(await api.GET('/api/v1/company/settings')),
  })
  useEffect(() => {
    const s = query.data
    if (!s) return
    form.setFieldsValue({
      working_weekdays: s.working_weekdays,
      shift: [dayjs(s.shift_start, 'HH:mm:ss'), dayjs(s.shift_end, 'HH:mm:ss')],
      cutover_time: dayjs(s.cutover_time, 'HH:mm:ss'),
      timezone: s.timezone,
    })
  }, [query.data, form])

  const save = useMutation({
    mutationFn: async (v: SettingsForm) =>
      unwrap(
        await api.PUT('/api/v1/company/settings', {
          body: {
            working_weekdays: v.working_weekdays,
            shift_start: v.shift[0].format('HH:mm:00'),
            shift_end: v.shift[1].format('HH:mm:00'),
            cutover_time: v.cutover_time.format('HH:mm:00'),
            timezone: v.timezone,
          },
        }),
      ),
    onSuccess: () => message.success('Đã lưu cấu hình'),
    onError: (e: Error) => message.error(e.message),
  })

  return (
    <Card title="Ca giao hàng" loading={query.isLoading}>
      <Form<SettingsForm> form={form} layout="vertical" style={{ maxWidth: 520 }} onFinish={(v) => save.mutate(v)}>
        <Form.Item name="working_weekdays" label="Ngày giao hàng trong tuần" rules={[{ required: true }]}>
          <Checkbox.Group options={WEEKDAYS} />
        </Form.Item>
        <Form.Item name="shift" label="Giờ làm việc" rules={[{ required: true }]}>
          <TimePicker.RangePicker format={T} minuteStep={15} />
        </Form.Item>
        <Form.Item
          name="cutover_time"
          label="Giờ cut-over"
          extra="Đơn nhận sau giờ này được đưa vào kế hoạch của ngày làm việc kế tiếp."
          rules={[{ required: true }]}
        >
          <TimePicker format={T} minuteStep={15} />
        </Form.Item>
        <Form.Item name="timezone" label="Múi giờ" rules={[{ required: true }]}>
          <Input style={{ width: 240 }} />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={save.isPending}>
          Lưu
        </Button>
      </Form>
    </Card>
  )
}

function ApiKeys() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [created, setCreated] = useState<string | null>(null)
  const keys = useQuery({
    queryKey: ['api-keys'],
    queryFn: async () => unwrap(await api.GET('/api/v1/api-keys')),
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['api-keys'] })
  const create = useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/v1/api-keys', { body: { name } })),
    onSuccess: async (k) => {
      setCreated(k.api_key)
      setName('')
      await refresh()
    },
    onError: (e: Error) => message.error(e.message),
  })
  const revoke = useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.POST('/api/v1/api-keys/{key_id}/revoke', { params: { path: { key_id: id } } })),
    onSuccess: refresh,
  })

  return (
    <Card title="API key tích hợp">
      <Typography.Paragraph type="secondary">
        Hệ thống bán hàng / quản lý kho dùng API key để đẩy đơn hàng, mặt hàng, tồn kho qua{' '}
        <Typography.Text code>POST /api/v1/integration/&#123;loại&#125;</Typography.Text> với header{' '}
        <Typography.Text code>X-API-Key</Typography.Text>.
      </Typography.Paragraph>
      <Space style={{ marginBottom: 16 }}>
        <Input placeholder="Tên hệ thống, vd. Phần mềm bán hàng" value={name} onChange={(e) => setName(e.target.value)} style={{ width: 300 }} />
        <Button type="primary" disabled={!name.trim()} loading={create.isPending} onClick={() => create.mutate()}>
          Tạo API key
        </Button>
      </Space>
      <Table<ApiKey>
        rowKey="id"
        size="small"
        pagination={false}
        loading={keys.isLoading}
        dataSource={keys.data}
        columns={[
          { title: 'Tên', dataIndex: 'name' },
          { title: 'Prefix', dataIndex: 'key_prefix', width: 110, render: (v: string) => <code>tms_{v}_…</code> },
          { title: 'Tạo lúc', dataIndex: 'created_at', width: 170, render: fmtDateTime },
          { title: 'Dùng gần nhất', dataIndex: 'last_used_at', width: 170, render: fmtDateTime },
          {
            title: '',
            width: 110,
            render: (_, k) =>
              k.is_active ? (
                <Popconfirm title="Thu hồi key này?" onConfirm={() => revoke.mutate(k.id)}>
                  <a>Thu hồi</a>
                </Popconfirm>
              ) : (
                <Tag>Đã thu hồi</Tag>
              ),
          },
        ]}
      />
      <Modal open={Boolean(created)} title="API key mới" footer={null} onCancel={() => setCreated(null)}>
        <Alert type="warning" showIcon title="Key chỉ hiển thị một lần. Hãy sao chép và lưu ở nơi an toàn." />
        <Typography.Paragraph copyable code style={{ marginTop: 16, wordBreak: 'break-all' }}>
          {created}
        </Typography.Paragraph>
      </Modal>
    </Card>
  )
}
