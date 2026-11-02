import { useMutation, useQueryClient } from '@tanstack/react-query'
import { App, Form, Modal, type FormInstance } from 'antd'
import { useState, type ReactNode } from 'react'

import { ApiError, blankToNull } from './api-helpers'

/**
 * Modal tạo/sửa dùng chung: `editing = null` → tạo mới, có giá trị → sửa.
 * `save` nhận giá trị form (+ bản ghi đang sửa) và gọi API.
 */
export function useEntityModal<T, V extends object>(opts: {
  queryKey: string
  title: string
  save: (values: V, editing: T | null) => Promise<unknown>
  toForm?: (record: T) => Partial<V>
  defaults?: Partial<V>
}) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<V>()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<T | null>(null)

  const mutation = useMutation({
    mutationFn: (values: V) => opts.save(blankToNull(values), editing),
    onSuccess: async () => {
      message.success('Đã lưu')
      setOpen(false)
      await queryClient.invalidateQueries({ queryKey: [opts.queryKey] })
    },
    onError: (e: Error) => {
      // Lỗi hiện dưới từng ô; thông báo chung liệt kê đủ, phòng khi trường không có trên form.
      message.error({ content: e.message, duration: 8 })
      if (e instanceof ApiError && e.fields.length) {
        const fields = e.fields.filter((f) => f.path.length)
        form.setFields(fields.map((f) => ({ name: f.path, errors: [f.message] })) as never)
        if (fields[0]) form.scrollToField(fields[0].path as never)
      }
    },
  })

  const show = (record: T | null) => {
    setEditing(record)
    form.resetFields()
    form.setFieldsValue((record ? opts.toForm?.(record) ?? record : opts.defaults ?? {}) as never)
    setOpen(true)
  }

  const render = (children: (form: FormInstance<V>, editing: T | null) => ReactNode, width = 560) => (
    <Modal
      open={open}
      title={`${editing ? 'Sửa' : 'Thêm'} ${opts.title}`}
      okText="Lưu"
      cancelText="Hủy"
      width={width}
      confirmLoading={mutation.isPending}
      onOk={() => form.submit()}
      onCancel={() => setOpen(false)}
      destroyOnHidden
    >
      <Form<V> form={form} layout="vertical" scrollToFirstError onFinish={(v) => mutation.mutate(v)}>
        {children(form, editing)}
      </Form>
    </Modal>
  )

  return { show, render }
}

export const mapLink = (lat: number | string, lng: number | string) =>
  `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=17/${lat}/${lng}`
