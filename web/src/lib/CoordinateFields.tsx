import { EnvironmentOutlined } from '@ant-design/icons'
import { Button, Col, Form, InputNumber, Modal, Row, Typography } from 'antd'
import { useState } from 'react'

import { MapView } from './MapView'

/** Cặp ô vĩ độ / kinh độ + chọn trên bản đồ (dùng chung cho kho và điểm giao). */
export function CoordinateFields({ prefix = [] }: { prefix?: (string | number)[] }) {
  const form = Form.useFormInstance()
  const [open, setOpen] = useState(false)
  const latName = [...prefix, 'latitude']
  const lngName = [...prefix, 'longitude']
  const lat = Form.useWatch(latName, form)
  const lng = Form.useWatch(lngName, form)
  const hasPoint = lat !== undefined && lat !== null && lat !== '' && lng !== undefined && lng !== ''

  return (
    <Row gutter={12} align="bottom">
      <Col span={10}>
        <Form.Item name={latName} label="Vĩ độ" rules={[{ required: true }]}>
          <InputNumber style={{ width: '100%' }} min={-90} max={90} step={0.000001} stringMode />
        </Form.Item>
      </Col>
      <Col span={10}>
        <Form.Item name={lngName} label="Kinh độ" rules={[{ required: true }]}>
          <InputNumber style={{ width: '100%' }} min={-180} max={180} step={0.000001} stringMode />
        </Form.Item>
      </Col>
      <Col span={4}>
        <Form.Item>
          <Button icon={<EnvironmentOutlined />} onClick={() => setOpen(true)} title="Chọn trên bản đồ" />
        </Form.Item>
      </Col>
      <Modal open={open} title="Chọn vị trí" footer={null} width={720} onCancel={() => setOpen(false)} destroyOnHidden>
        <Typography.Paragraph type="secondary">Bấm vào bản đồ để đặt vị trí.</Typography.Paragraph>
        <MapView
          markers={hasPoint ? [{ id: 'p', lat: Number(lat), lng: Number(lng), label: '●' }] : []}
          onPick={(la, ln) => {
            form.setFieldValue(latName, la.toFixed(6))
            form.setFieldValue(lngName, ln.toFixed(6))
          }}
        />
      </Modal>
    </Row>
  )
}
