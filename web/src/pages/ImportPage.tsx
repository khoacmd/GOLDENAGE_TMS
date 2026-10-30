import { DownloadOutlined, UploadOutlined } from '@ant-design/icons'
import type { components } from '@tms/api-client'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Col, Result, Row, Select, Space, Table, Tag, Typography, Upload } from 'antd'
import type { UploadFile } from 'antd'
import { useState } from 'react'

import { api, tokenStore } from '../api'
import { unwrap, usePaging } from '../lib/api-helpers'
import { IMPORT_STATUS, fmtDateTime } from '../lib/labels'

type Kind = components['schemas']['ImportKind']
type ImportResult = components['schemas']['ImportResultOut']
type Job = components['schemas']['ImportJobOut']
type RowError = components['schemas']['RowErrorOut']

async function authFetch(path: string, init?: RequestInit) {
  const headers = new Headers(init?.headers)
  const token = tokenStore.get()?.access_token
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return fetch(path, { ...init, headers })
}

export function ImportPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [kind, setKind] = useState<Kind>('warehouses')
  const [file, setFile] = useState<UploadFile | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const paging = usePaging(10)

  const specs = useQuery({
    queryKey: ['import-specs'],
    queryFn: async () => unwrap(await api.GET('/api/v1/imports/specs')),
  })
  const jobs = useQuery({
    queryKey: ['import-jobs', paging.params],
    queryFn: async () => unwrap(await api.GET('/api/v1/imports/jobs', { params: { query: paging.params } })),
  })
  const spec = specs.data?.find((s) => s.kind === kind)
  const titleOf = (k: Kind) => specs.data?.find((s) => s.kind === k)?.title ?? k

  const run = useMutation({
    // Upload multipart: gọi fetch trực tiếp (openapi-fetch không tự dựng FormData).
    mutationFn: async (dryRun: boolean) => {
      const body = new FormData()
      body.append('file', file!.originFileObj as File)
      const resp = await authFetch(`/api/v1/imports/${kind}?dry_run=${dryRun}`, { method: 'POST', body })
      const json = await resp.json()
      if (!resp.ok) throw new Error(json?.error?.message ?? 'Import thất bại')
      return json as ImportResult
    },
    onSuccess: async (data) => {
      setResult(data)
      await queryClient.invalidateQueries({ queryKey: ['import-jobs'] })
      if (data.status === 'SUCCEEDED') {
        message.success(`Đã nhập: ${data.created} mới, ${data.updated} cập nhật`)
        await queryClient.invalidateQueries()
      }
    },
    onError: (e: Error) => message.error(e.message),
  })

  async function downloadTemplate() {
    const resp = await authFetch(`/api/v1/imports/templates/${kind}`)
    const url = URL.createObjectURL(await resp.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = `tms-template-${kind}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card title="Import dữ liệu">
        <Row gutter={[24, 16]}>
          <Col xs={24} lg={10}>
            <Space orientation="vertical" style={{ width: '100%' }}>
              <Typography.Text strong>1. Chọn loại dữ liệu</Typography.Text>
              <Select<Kind>
                style={{ width: '100%' }}
                value={kind}
                onChange={(k) => {
                  setKind(k)
                  setResult(null)
                }}
                options={specs.data?.map((s) => ({ value: s.kind, label: s.title }))}
              />
              {spec && <Typography.Paragraph type="secondary">{spec.description}</Typography.Paragraph>}
              <Typography.Text strong>2. Tải template, điền dữ liệu</Typography.Text>
              <Button icon={<DownloadOutlined />} onClick={downloadTemplate}>
                Tải template Excel
              </Button>
              <Typography.Text strong>3. Chọn file (.xlsx, .csv) và kiểm tra trước khi nhập</Typography.Text>
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
              <Space>
                <Button disabled={!file} loading={run.isPending && run.variables} onClick={() => run.mutate(true)}>
                  Kiểm tra
                </Button>
                <Button type="primary" disabled={!file} loading={run.isPending && !run.variables} onClick={() => run.mutate(false)}>
                  Nhập dữ liệu
                </Button>
              </Space>
            </Space>
          </Col>
          <Col xs={24} lg={14}>
            {result ? <ResultView result={result} /> : spec && <ColumnsView columns={spec.columns} />}
          </Col>
        </Row>
      </Card>

      <Card title="Lịch sử import">
        <Table<Job>
          rowKey="id"
          size="small"
          loading={jobs.isLoading}
          dataSource={jobs.data?.items}
          pagination={paging.pagination(jobs.data?.total)}
          scroll={{ x: 800 }}
          columns={[
            { title: 'Thời điểm', dataIndex: 'created_at', width: 170, render: fmtDateTime },
            { title: 'Loại', dataIndex: 'kind', width: 160, render: titleOf },
            { title: 'Nguồn', width: 160, render: (_, j) => (j.source === 'API' ? 'API tích hợp' : j.filename) },
            {
              title: 'Kết quả',
              dataIndex: 'status',
              width: 120,
              render: (v: Job['status']) => <Tag color={IMPORT_STATUS[v].color}>{IMPORT_STATUS[v].label}</Tag>,
            },
            { title: 'Số dòng', dataIndex: 'total_rows', width: 80, align: 'right' },
            { title: 'Mới', dataIndex: 'created_count', width: 70, align: 'right' },
            { title: 'Cập nhật', dataIndex: 'updated_count', width: 90, align: 'right' },
            { title: 'Lỗi', dataIndex: 'error_count', width: 70, align: 'right' },
          ]}
        />
      </Card>
    </Space>
  )
}

function ColumnsView({ columns }: { columns: components['schemas']['ColumnOut'][] }) {
  return (
    <Table
      rowKey="key"
      size="small"
      pagination={false}
      dataSource={columns}
      columns={[
        {
          title: 'Cột',
          dataIndex: 'label',
          render: (v: string, c) => (c.required ? <Typography.Text strong>{v} *</Typography.Text> : v),
        },
        { title: 'Mô tả', dataIndex: 'description' },
        { title: 'Ví dụ', dataIndex: 'example', render: (v: unknown) => (v === null ? '' : String(v)) },
      ]}
    />
  )
}

function ResultView({ result }: { result: ImportResult }) {
  if (result.status !== 'FAILED') {
    return (
      <Result
        status="success"
        title={result.dry_run ? 'Dữ liệu hợp lệ, sẵn sàng nhập' : 'Nhập dữ liệu thành công'}
        subTitle={`${result.total_rows} dòng · ${result.created} mới · ${result.updated} cập nhật`}
      />
    )
  }
  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Alert
        type="error"
        showIcon
        title={`Có ${result.errors.length} lỗi - chưa có dữ liệu nào được ghi`}
        description="Sửa các lỗi dưới đây trong file rồi kiểm tra lại."
      />
      <Table<RowError>
        rowKey={(e, i) => `${e.row}-${e.column}-${i}`}
        size="small"
        dataSource={result.errors}
        pagination={{ pageSize: 20, hideOnSinglePage: true }}
        columns={[
          { title: 'Dòng', dataIndex: 'row', width: 70, render: (v: number) => (v > 0 ? v : '') },
          { title: 'Cột', dataIndex: 'column', width: 160 },
          { title: 'Lỗi', dataIndex: 'message' },
        ]}
      />
    </Space>
  )
}
