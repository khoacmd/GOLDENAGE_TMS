import { DownloadOutlined, SwapOutlined, UploadOutlined } from '@ant-design/icons'
import type { components } from '@tms/api-client'
import { useMutation } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Form,
  InputNumber,
  Row,
  Space,
  Typography,
  Upload,
} from 'antd'
import type { UploadFile } from 'antd'
import type { Dayjs } from 'dayjs'
import { useState } from 'react'
import { Link } from 'react-router'

import { api } from '../../api'
import { unwrap } from '../../lib/api-helpers'
import { fmtDate, fmtNumber } from '../../lib/labels'
import { download } from './download'

type Conversion = components['schemas']['DmsOrdersConversionOut']

export function DmsOrdersPage() {
  const { message } = App.useApp()
  const [file, setFile] = useState<UploadFile | null>(null)
  const [deliveryDate, setDeliveryDate] = useState<Dayjs | null>(null)
  const [codeLength, setCodeLength] = useState<number | null>(18)
  const [result, setResult] = useState<Conversion | null>(null)

  const run = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/v1/conversions/dms-orders', {
          params: {
            query: {
              delivery_date: deliveryDate?.format('YYYY-MM-DD'),
              product_code_length: codeLength ?? 0,
            },
          },
          // Schema khai báo file là chuỗi nhị phân; thực tế gửi File qua multipart (mặc định là JSON).
          body: { file: file!.originFileObj as unknown as string },
          bodySerializer: (body) => {
            const form = new FormData()
            form.append('file', body.file as unknown as File)
            return form
          },
        }),
      ),
    onSuccess: (data) => {
      setResult(data)
      download(data)
      message.success(`Đã chuyển đổi ${data.orders} đơn hàng`)
    },
    onError: (e: Error) => message.error(e.message),
  })

  const reset = () => setResult(null)

  return (
    <Card title="Chuyển đổi dữ liệu đơn hàng từ DMS">
      <Row gutter={[24, 16]}>
        <Col xs={24} lg={10}>
          <Typography.Paragraph type="secondary">
            Chuyển file đơn hàng tải từ DMS (báo cáo đơn bán hàng) sang template import đơn hàng. Chức năng chỉ
            đổi định dạng, không ghi dữ liệu: tải file kết quả về rồi nhập ở màn hình{' '}
            <Link to="/imports">Import dữ liệu</Link> (loại Đơn hàng).
          </Typography.Paragraph>
          <Form layout="vertical">
            <Form.Item label="File đơn hàng DMS (.xlsx, .csv)">
              <Upload
                accept=".xlsx,.csv"
                maxCount={1}
                beforeUpload={() => false}
                fileList={file ? [file] : []}
                onChange={({ fileList }) => {
                  setFile(fileList.at(-1) ?? null)
                  reset()
                }}
              >
                <Button icon={<UploadOutlined />}>Chọn file</Button>
              </Upload>
            </Form.Item>
            <Form.Item
              label="Ngày giao yêu cầu"
              extra="Bỏ trống: theo ngày tạo phiếu giao trên DMS (không có thì lấy ngày đặt)."
            >
              <DatePicker
                format="DD/MM/YYYY"
                value={deliveryDate}
                onChange={(d) => {
                  setDeliveryDate(d)
                  reset()
                }}
                placeholder="Theo file"
              />
            </Form.Item>
            <Form.Item
              label="Độ dài mã hàng"
              extra="Mã hàng toàn số được thêm số 0 bên trái cho đủ độ dài này, khớp mã trong Dữ liệu gốc. 0 = giữ nguyên."
            >
              <InputNumber
                min={0}
                max={40}
                value={codeLength}
                onChange={(v) => {
                  setCodeLength(v)
                  reset()
                }}
              />
            </Form.Item>
            <Button
              type="primary"
              icon={<SwapOutlined />}
              disabled={!file}
              loading={run.isPending}
              onClick={() => run.mutate()}
            >
              Chuyển đổi và tải file
            </Button>
          </Form>
        </Col>
        <Col xs={24} lg={14}>
          {result ? (
            <Space orientation="vertical" style={{ width: '100%' }}>
              <Descriptions bordered size="small" column={1} title="Kết quả">
                <Descriptions.Item label="File">{result.filename}</Descriptions.Item>
                <Descriptions.Item label="Đơn hàng">{fmtNumber(result.orders)}</Descriptions.Item>
                <Descriptions.Item label="Dòng mặt hàng">{fmtNumber(result.lines)}</Descriptions.Item>
                <Descriptions.Item label="Khách hàng">{fmtNumber(result.customers)}</Descriptions.Item>
                <Descriptions.Item label="Mặt hàng">{fmtNumber(result.products)}</Descriptions.Item>
                <Descriptions.Item label="Tổng giá trị (đ)">{fmtNumber(result.total_value)}</Descriptions.Item>
                <Descriptions.Item label="Ngày giao yêu cầu">
                  {result.first_delivery_date === result.last_delivery_date
                    ? fmtDate(result.first_delivery_date)
                    : `${fmtDate(result.first_delivery_date)} - ${fmtDate(result.last_delivery_date)}`}
                </Descriptions.Item>
                <Descriptions.Item label="Bỏ qua">
                  {result.skipped_zero_qty} dòng số lượng 0, {result.skipped_returns} dòng hàng trả
                </Descriptions.Item>
              </Descriptions>
              {result.warnings.map((w) => (
                <Alert key={w} type="warning" showIcon title={w} />
              ))}
              <Space wrap>
                <Button icon={<DownloadOutlined />} onClick={() => download(result)}>
                  Tải lại file
                </Button>
                <Link to="/imports">
                  <Button type="primary">Đến Import dữ liệu</Button>
                </Link>
              </Space>
            </Space>
          ) : (
            <Alert
              type="info"
              showIcon
              title="Quy tắc chuyển đổi"
              description={
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  <li>Số đơn = OrderNbr, Mã KH = CustomerCD, Ngày đặt = OrderDate.</li>
                  <li>Số lượng = số lượng bán + hàng tặng; thành tiền = số lượng bán × đơn giá.</li>
                  <li>Cùng mặt hàng nhiều dòng trong 1 đơn được gộp; bỏ dòng số lượng 0 và hàng trả.</li>
                  <li>File kết quả được kiểm tra theo template trước khi tải về.</li>
                </ul>
              }
            />
          )}
        </Col>
      </Row>
    </Card>
  )
}
