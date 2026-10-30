import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { Navigate } from 'react-router'

import { LoginError, useAuth } from '../auth-context'

interface LoginForm {
  username: string
  password: string
  companyCode?: string
}

export function LoginPage() {
  const { me, login } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [needCompany, setNeedCompany] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  if (me) return <Navigate to="/" replace />

  async function onFinish(values: LoginForm) {
    setSubmitting(true)
    setError(null)
    try {
      await login(values.username, values.password, values.companyCode)
    } catch (e) {
      if (e instanceof LoginError && e.code === 'company_required') setNeedCompany(true)
      setError(e instanceof Error ? e.message : 'Đăng nhập thất bại')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 16 }}>
      <Card style={{ width: '100%', maxWidth: 380 }}>
        <Typography.Title level={3} style={{ textAlign: 'center' }}>
          TMS - Quản lý giao hàng
        </Typography.Title>
        {error && <Alert type="error" title={error} showIcon style={{ marginBottom: 16 }} />}
        <Form<LoginForm> layout="vertical" onFinish={onFinish} disabled={submitting}>
          <Form.Item name="username" label="Tên đăng nhập" rules={[{ required: true }]}>
            <Input autoFocus autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="Mật khẩu" rules={[{ required: true }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          {needCompany && (
            <Form.Item name="companyCode" label="Mã công ty" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          )}
          <Button type="primary" htmlType="submit" block loading={submitting}>
            Đăng nhập
          </Button>
        </Form>
      </Card>
    </div>
  )
}
