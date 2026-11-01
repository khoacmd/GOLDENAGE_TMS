import { useMutation } from '@tanstack/react-query'
import { App, Form, Input, Modal } from 'antd'

import { api, tokenStore } from '../api'
import { unwrap } from '../lib/api-helpers'

interface Values {
  current_password: string
  new_password: string
  confirm: string
}

/** Người dùng tự đổi mật khẩu; phiên hiện tại nhận token mới, các phiên khác bị đăng xuất. */
export function ChangePasswordModal({ open, onClose }: { open: boolean; onClose(): void }) {
  const { message } = App.useApp()
  const [form] = Form.useForm<Values>()

  const mutation = useMutation({
    mutationFn: async ({ current_password, new_password }: Values) =>
      unwrap(await api.POST('/api/v1/auth/change-password', { body: { current_password, new_password } })),
    onSuccess: (tokens) => {
      tokenStore.set(tokens)
      message.success('Đã đổi mật khẩu. Các phiên đăng nhập khác đã bị đăng xuất.')
      onClose()
    },
    onError: (e: Error) => message.error(e.message),
  })

  return (
    <Modal
      open={open}
      title="Đổi mật khẩu"
      okText="Đổi mật khẩu"
      cancelText="Hủy"
      confirmLoading={mutation.isPending}
      onOk={() => form.submit()}
      onCancel={onClose}
      afterClose={() => form.resetFields()}
      destroyOnHidden
    >
      <Form<Values> form={form} layout="vertical" onFinish={(v) => mutation.mutate(v)}>
        <Form.Item name="current_password" label="Mật khẩu hiện tại" rules={[{ required: true }]}>
          <Input.Password autoComplete="current-password" autoFocus />
        </Form.Item>
        <Form.Item
          name="new_password"
          label="Mật khẩu mới"
          rules={[
            { required: true },
            { min: 8, message: 'Tối thiểu 8 ký tự' },
            { max: 128, message: 'Tối đa 128 ký tự' },
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm"
          label="Nhập lại mật khẩu mới"
          dependencies={['new_password']}
          rules={[
            { required: true },
            ({ getFieldValue }) => ({
              validator: (_, value) =>
                !value || value === getFieldValue('new_password')
                  ? Promise.resolve()
                  : Promise.reject(new Error('Mật khẩu nhập lại không khớp')),
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  )
}
