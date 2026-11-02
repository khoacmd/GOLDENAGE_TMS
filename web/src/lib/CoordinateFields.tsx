import { EnvironmentOutlined } from '@ant-design/icons'
import { Button, Col, Form, InputNumber, Modal, Row, Typography } from 'antd'
import { useState } from 'react'

import { MapView } from './MapView'

/**
 * Cặp ô vĩ độ / kinh độ + chọn trên bản đồ (dùng chung cho kho và điểm giao).
 * Trong `Form.List`: `prefix` là tên tương đối cho `Form.Item`, `listPath` là đường dẫn của list -
 * `form.setFieldValue`/`useWatch` luôn dùng đường dẫn tuyệt đối từ gốc form.
 */
export function CoordinateFields({
  prefix = [],
  listPath = [],
}: {
  prefix?: (string | number)[]
  listPath?: (string | number)[]
}) {
  const form = Form.useFormInstance()
  const [open, setOpen] = useState(false)
  const latName = [...prefix, 'latitude']
  const lngName = [...prefix, 'longitude']
  const latPath = [...listPath, ...latName]
  const lngPath = [...listPath, ...lngName]
  const lat = Form.useWatch(latPath, form)
  const lng = Form.useWatch(lngPath, form)
  const hasPoint = lat !== undefined && lat !== null && lat !== '' && lng !== undefined && lng !== null && lng !== ''

  return (
    <Row gutter={12} align="bottom">
      <Col span={10}>
        <Form.Item name={latName} label="Vĩ độ" rules={[{ required: true }]}>
          <InputNumber style={{ width: '100%' }} min={-90} max={90} step={0.000001} precision={6} stringMode />
        </Form.Item>
      </Col>
      <Col span={10}>
        <Form.Item name={lngName} label="Kinh độ" rules={[{ required: true }]}>
          <InputNumber style={{ width: '100%' }} min={-180} max={180} step={0.000001} precision={6} stringMode />
        </Form.Item>
      </Col>
      <Col span={4}>
        <Form.Item>
          <Button icon={<EnvironmentOutlined />} onClick={() => setOpen(true)} title="Chọn trên bản đồ" />
        </Form.Item>
      </Col>
      <Modal
        open={open}
        title="Chọn vị trí"
        width={720}
        onCancel={() => setOpen(false)}
        footer={
          <Button type="primary" onClick={() => setOpen(false)}>
            Xong
          </Button>
        }
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">
          {hasPoint ? `Vị trí đã chọn: ${lat}, ${lng}. Bấm chỗ khác để đổi.` : 'Bấm vào bản đồ để đặt vị trí.'}
        </Typography.Paragraph>
        <MapView
          markers={hasPoint ? [{ id: 'p', lat: Number(lat), lng: Number(lng), label: '●' }] : []}
          onPick={(la, ln) => {
            form.setFieldValue(latPath, la.toFixed(6))
            form.setFieldValue(lngPath, ln.toFixed(6))
          }}
        />
      </Modal>
    </Row>
  )
}
