import { DeleteOutlined, UploadOutlined } from '@ant-design/icons'
import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Col, Form, Input, Popconfirm, Row, Space, Typography, Upload } from 'antd'
import { useEffect } from 'react'

import { api } from '../api'
import { unwrap } from '../lib/api-helpers'
import { PrintHeader } from './plans/PrintPages'

type Templates = components['schemas']['PrintTemplates']
type Profile = components['schemas']['PrintProfileOut']

const DOCS = [
  { prefix: 'delivery', title: 'Phiếu giao hàng' },
  { prefix: 'picking', title: 'Phiếu soạn hàng' },
] as const

/** Logo + đầu/chân trang của phiếu soạn hàng và phiếu giao hàng (admin công ty). */
export function PrintTemplatesCard() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<Templates>()
  const query = useQuery({
    queryKey: ['print-profile'],
    queryFn: async () => unwrap(await api.GET('/api/v1/company/print-profile')),
  })
  useEffect(() => {
    if (query.data) form.setFieldsValue(query.data)
  }, [query.data, form])
  const values = Form.useWatch([], form)

  const done = (text: string) => (data: Profile) => {
    queryClient.setQueryData(['print-profile'], data)
    message.success(text)
  }
  const save = useMutation({
    mutationFn: async (v: Templates) => unwrap(await api.PUT('/api/v1/company/print-profile', { body: v })),
    onSuccess: done('Đã lưu mẫu phiếu in'),
    onError: (e: Error) => message.error(e.message),
  })
  const upload = useMutation({
    mutationFn: async (file: File) =>
      unwrap(
        await api.PUT('/api/v1/company/logo', {
          // Schema khai báo file là chuỗi nhị phân; thực tế gửi File qua multipart.
          body: { file: file as unknown as string },
          bodySerializer: (body) => {
            const data = new FormData()
            data.append('file', body.file as unknown as File)
            return data
          },
        }),
      ),
    onSuccess: done('Đã cập nhật logo'),
    onError: (e: Error) => message.error(e.message),
  })
  const removeLogo = useMutation({
    mutationFn: async () => unwrap(await api.DELETE('/api/v1/company/logo')),
    onSuccess: done('Đã xóa logo'),
    onError: (e: Error) => message.error(e.message),
  })

  const profile = query.data
  return (
    <Card title="Mẫu phiếu in" loading={query.isLoading}>
      <Typography.Paragraph type="secondary">
        Logo và đầu trang in ở đầu phiếu (dòng đầu in đậm, bỏ trống = tên công ty); chân trang in ở cuối mọi trang,
        bên phải là số trang. Phiếu in khổ A4 (máy in kim hoặc laser).
      </Typography.Paragraph>
      <Space align="center" wrap style={{ marginBottom: 16 }}>
        <span>Logo:</span>
        {profile?.logo ? (
          <img src={profile.logo} alt="Logo" style={{ height: 48, maxWidth: 160, objectFit: 'contain', border: '1px solid #eee' }} />
        ) : (
          <Typography.Text type="secondary">Chưa có</Typography.Text>
        )}
        <Upload
          accept="image/png,image/jpeg,image/webp"
          showUploadList={false}
          beforeUpload={(file) => {
            upload.mutate(file)
            return false
          }}
        >
          <Button icon={<UploadOutlined />} loading={upload.isPending}>
            {profile?.logo ? 'Đổi logo' : 'Tải logo'}
          </Button>
        </Upload>
        {profile?.logo && (
          <Popconfirm title="Xóa logo?" onConfirm={() => removeLogo.mutate()}>
            <Button icon={<DeleteOutlined />} loading={removeLogo.isPending}>
              Xóa
            </Button>
          </Popconfirm>
        )}
        <Typography.Text type="secondary">PNG, JPEG hoặc WebP, tối đa 512 KB; nên dùng logo đen trắng cho máy in kim.</Typography.Text>
      </Space>
      <Form<Templates> form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Row gutter={24}>
          {DOCS.map(({ prefix, title }) => (
            <Col key={prefix} xs={24} lg={12}>
              <Typography.Title level={5}>{title}</Typography.Title>
              <Form.Item name={`${prefix}_header`} label="Đầu trang">
                <Input.TextArea
                  autoSize={{ minRows: 3, maxRows: 6 }}
                  maxLength={2000}
                  placeholder={'CÔNG TY ...\nĐịa chỉ: ...\nĐiện thoại: ... - MST: ...'}
                />
              </Form.Item>
              <Form.Item name={`${prefix}_footer`} label="Chân trang">
                <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} maxLength={2000} placeholder="Hotline: ..." />
              </Form.Item>
              {profile && (
                <div style={{ border: '1px dashed #bbb', padding: 8, marginBottom: 16, background: '#fff', color: '#000' }}>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    Xem trước đầu trang
                  </Typography.Text>
                  <PrintHeader profile={profile} text={values?.[`${prefix}_header`]?.trim() || null} />
                </div>
              )}
            </Col>
          ))}
        </Row>
        <Button type="primary" htmlType="submit" loading={save.isPending}>
          Lưu mẫu phiếu
        </Button>
      </Form>
    </Card>
  )
}
