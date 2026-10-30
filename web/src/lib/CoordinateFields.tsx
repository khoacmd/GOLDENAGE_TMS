import { Col, Form, InputNumber, Row } from 'antd'

/** Cặp ô vĩ độ / kinh độ (dùng chung cho kho và điểm giao). */
export function CoordinateFields({ prefix = [] }: { prefix?: (string | number)[] }) {
  return (
    <Row gutter={12}>
      <Col span={12}>
        <Form.Item name={[...prefix, 'latitude']} label="Vĩ độ" rules={[{ required: true }]}>
          <InputNumber style={{ width: '100%' }} min={-90} max={90} step={0.000001} stringMode />
        </Form.Item>
      </Col>
      <Col span={12}>
        <Form.Item name={[...prefix, 'longitude']} label="Kinh độ" rules={[{ required: true }]}>
          <InputNumber style={{ width: '100%' }} min={-180} max={180} step={0.000001} stringMode />
        </Form.Item>
      </Col>
    </Row>
  )
}
