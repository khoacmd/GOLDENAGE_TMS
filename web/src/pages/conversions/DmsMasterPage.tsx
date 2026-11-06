import { DownloadOutlined, SwapOutlined, UploadOutlined } from '@ant-design/icons'
import type { components } from '@tms/api-client'
import { useMutation } from '@tanstack/react-query'
import { Alert, App, Button, Card, Col, Descriptions, Form, InputNumber, Row, Space, Typography, Upload } from 'antd'
import type { UploadFile } from 'antd'
import { useState } from 'react'
import { Link } from 'react-router'

import { api } from '../../api'
import { unwrap } from '../../lib/api-helpers'
import { fmtNumber } from '../../lib/labels'
import { download } from './download'

type Conversion = components['schemas']['DmsMasterConversionOut']
type Kind = 'customers' | 'products'

const TEXT: Record<Kind, { title: string; noun: string; rules: string[] }> = {
  customers: {
    title: 'Chuyển đổi dữ liệu khách hàng từ DMS',
    noun: 'khách hàng',
    rules: [
      'Mã KH, Tên KH, Địa chỉ, NV sales lấy từ file DMS; mỗi khách 1 điểm giao DG1 (mặc định) cùng tên và địa chỉ.',
      'DMS không có tọa độ và thường chỉ ghi số nhà: cần điền Vĩ độ, Kinh độ, địa chỉ đầy đủ trước khi import.',
    ],
  },
  products: {
    title: 'Chuyển đổi dữ liệu mặt hàng từ DMS',
    noun: 'mặt hàng',
    rules: [
      'Mã hàng (thêm số 0 bên trái), Tên, Loại hàng, Nhà máy, Nhóm sản phẩm lấy từ file DMS; Đơn vị tính mặc định Thùng.',
      'SL SKU quy đổi = UnitRate của DMS khi lớn hơn 1, còn lại để trống.',
      'DMS không có trọng lượng và đơn vị SKU: cần điền trước khi import.',
    ],
  },
}

/** Lọc khách hàng / mặt hàng chưa có trong hệ thống từ file đơn hàng DMS sang template import. */
export function DmsMasterPage({ kind }: { kind: Kind }) {
  const { message } = App.useApp()
  const [file, setFile] = useState<UploadFile | null>(null)
  const [codeLength, setCodeLength] = useState<number | null>(18)
  const [result, setResult] = useState<Conversion | null>(null)
  const text = TEXT[kind]

  const run = useMutation({
    mutationFn: async () => {
      const options = {
        // Schema khai báo file là chuỗi nhị phân; thực tế gửi File qua multipart (mặc định là JSON).
        body: { file: file!.originFileObj as unknown as string },
        bodySerializer: (body: { file: string }) => {
          const form = new FormData()
          form.append('file', body.file as unknown as File)
          return form
        },
      }
      return unwrap(
        kind === 'customers'
          ? await api.POST('/api/v1/conversions/dms-customers', options)
          : await api.POST('/api/v1/conversions/dms-products', {
              ...options,
              params: { query: { product_code_length: codeLength ?? 0 } },
            }),
      )
    },
    onSuccess: (data) => {
      setResult(data)
      if (data.new) {
        download(data)
        message.success(`Đã lọc ${data.new} ${text.noun} mới`)
      } else {
        message.info(`Mọi ${text.noun} trong file đã có trong hệ thống`)
      }
    },
    onError: (e: Error) => message.error(e.message),
  })

  return (
    <Card title={text.title}>
      <Row gutter={[24, 16]}>
        <Col xs={24} lg={10}>
          <Typography.Paragraph type="secondary">
            Lọc các {text.noun} <b>chưa có trong hệ thống</b> từ file đơn hàng tải từ DMS, đưa vào template import{' '}
            {text.noun}. Chức năng không ghi dữ liệu: tải file về, điền các ô tô vàng (liệt kê ở sheet "Cần bổ sung")
            rồi nhập ở màn hình <Link to="/imports">Import dữ liệu</Link>.
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
                  setResult(null)
                }}
              >
                <Button icon={<UploadOutlined />}>Chọn file</Button>
              </Upload>
            </Form.Item>
            {kind === 'products' && (
              <Form.Item
                label="Độ dài mã hàng"
                extra="Mã hàng toàn số được thêm số 0 bên trái cho đủ độ dài này. 0 = giữ nguyên."
              >
                <InputNumber
                  min={0}
                  max={40}
                  value={codeLength}
                  onChange={(v) => {
                    setCodeLength(v)
                    setResult(null)
                  }}
                />
              </Form.Item>
            )}
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
                {result.new > 0 && <Descriptions.Item label="File">{result.filename}</Descriptions.Item>}
                <Descriptions.Item label={`Số ${text.noun} trong file`}>{fmtNumber(result.total)}</Descriptions.Item>
                <Descriptions.Item label="Đã có trong hệ thống (bỏ qua)">{fmtNumber(result.existing)}</Descriptions.Item>
                <Descriptions.Item label="Mới, đưa vào file">{fmtNumber(result.new)}</Descriptions.Item>
                <Descriptions.Item label="Còn thiếu thông tin bắt buộc">{fmtNumber(result.incomplete)}</Descriptions.Item>
              </Descriptions>
              {result.warnings.map((w) => (
                <Alert key={w} type="warning" showIcon title={w} />
              ))}
              {result.new > 0 && (
                <Space wrap>
                  <Button icon={<DownloadOutlined />} onClick={() => download(result)}>
                    Tải lại file
                  </Button>
                  <Link to="/imports">
                    <Button type="primary">Đến Import dữ liệu</Button>
                  </Link>
                </Space>
              )}
            </Space>
          ) : (
            <Alert
              type="info"
              showIcon
              title="Quy tắc chuyển đổi"
              description={
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {text.rules.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                  <li>Bỏ qua mã đã có trong hệ thống (kể cả đang ngưng hoạt động) để không ghi đè dữ liệu đã chỉnh.</li>
                </ul>
              }
            />
          )}
        </Col>
      </Row>
    </Card>
  )
}
