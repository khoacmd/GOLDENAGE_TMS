import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { components } from '@tms/api-client'
import { App, Modal, Popconfirm, QRCode, Space, Typography } from 'antd'
import { useState } from 'react'

import { fmtDateTime } from './labels'
import type { ZaloInfo } from './zalo'

type ActivationCode = components['schemas']['ActivationCodeOut']

/**
 * Cấp mã kích hoạt / thu hồi liên kết Zalo Mini App (admin công ty).
 * Mã chỉ hiện 1 lần trong hộp thoại sau khi tạo (server chỉ lưu hash).
 */
export function useZaloActivation(opts: {
  queryKey: string
  issue: (id: string) => Promise<ActivationCode>
  revoke: (id: string) => Promise<unknown>
}) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [shown, setShown] = useState<{ name: string; code: ActivationCode } | null>(null)
  const refresh = () => queryClient.invalidateQueries({ queryKey: [opts.queryKey] })

  const issue = useMutation({
    mutationFn: async ({ id }: { id: string; name: string }) => opts.issue(id),
    onSuccess: async (code, { name }) => {
      setShown({ name, code })
      await refresh()
    },
    onError: (e: Error) => message.error(e.message),
  })
  const revoke = useMutation({
    mutationFn: async (id: string) => opts.revoke(id),
    onSuccess: async () => {
      message.success('Đã thu hồi liên kết Zalo')
      await refresh()
    },
    onError: (e: Error) => message.error(e.message),
  })

  const actions = (id: string, name: string, info: ZaloInfo = { status: 'NOT_INVITED' }) => (
    <Space size="small" wrap>
      <Popconfirm
        title={info.status === 'NOT_INVITED' ? `Cấp mã kích hoạt cho ${name}?` : `Cấp mã mới cho ${name}?`}
        description={info.status === 'NOT_INVITED' ? undefined : 'Mã chưa dùng trước đó sẽ mất hiệu lực.'}
        onConfirm={() => issue.mutate({ id, name })}
      >
        <a>{info.status === 'NOT_INVITED' ? 'Cấp mã' : 'Cấp lại mã'}</a>
      </Popconfirm>
      {info.status !== 'NOT_INVITED' && (
        <Popconfirm
          title={`Thu hồi Zalo của ${name}?`}
          description="Zalo đã liên kết không xem được nữa; mã chưa dùng mất hiệu lực."
          onConfirm={() => revoke.mutate(id)}
        >
          <a>Thu hồi</a>
        </Popconfirm>
      )}
    </Space>
  )

  const modal = (
    <Modal
      open={Boolean(shown)}
      title={`Mã kích hoạt Zalo - ${shown?.name ?? ''}`}
      onCancel={() => setShown(null)}
      onOk={() => setShown(null)}
      okText="Đã gửi mã"
      cancelButtonProps={{ style: { display: 'none' } }}
    >
      {shown && (
        <Space orientation="vertical" align="center" style={{ width: '100%' }}>
          <Typography.Title level={2} copyable style={{ letterSpacing: 4, margin: 0 }}>
            {shown.code.code}
          </Typography.Title>
          <QRCode value={shown.code.link ?? shown.code.code} />
          {shown.code.link && (
            <Typography.Text copyable={{ text: shown.code.link }} type="secondary">
              Link mở Zalo Mini App
            </Typography.Text>
          )}
          <Typography.Text type="secondary">
            Dùng 1 lần, hết hạn {fmtDateTime(shown.code.expires_at)}. Gửi mã (hoặc QR) cho người dùng để nhập trên
            Zalo Mini App. Mã chỉ hiển thị lần này.
          </Typography.Text>
        </Space>
      )}
    </Modal>
  )

  return { actions, modal }
}
