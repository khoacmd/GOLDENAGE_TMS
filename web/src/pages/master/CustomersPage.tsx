import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import type { components } from '@tms/api-client'
import { useQuery } from '@tanstack/react-query'
import {
  Button,
  Card,
  Checkbox,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
} from 'antd'

import { api } from '../../api'
import { useAuth } from '../../auth-context'
import { unwrap, usePaging } from '../../lib/api-helpers'
import { CoordinateFields } from '../../lib/CoordinateFields'
import { mapLink, useEntityModal } from '../../lib/crud'
import { VEHICLE_REQUIREMENT, WEEKDAYS, options, weekdayText } from '../../lib/labels'

type Customer = components['schemas']['CustomerOut']
type CustomerForm = components['schemas']['CustomerCreate']
type Point = components['schemas']['DeliveryPointOut']

export function CustomersPage() {
  const { hasRole } = useAuth()
  const canEdit = hasRole('company_admin', 'manager')
  const paging = usePaging()
  const query = useQuery({
    queryKey: ['customers', paging.params],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/customers', { params: { query: paging.params } })),
  })

  const modal = useEntityModal<Customer, CustomerForm>({
    queryKey: 'customers',
    title: 'khách hàng',
    defaults: {
      is_active: true,
      required_vehicle_type: 'ANY',
      delivery_weekdays: [],
      delivery_points: [{ code: 'DG1', is_default: true, is_active: true } as never],
    },
    // Chỉ sửa các điểm đang hoạt động; điểm bị xóa khỏi form sẽ bị ngưng hoạt động.
    toForm: (c) => ({ ...c, delivery_points: c.delivery_points.filter((p) => p.is_active) }) as never,
    save: async (values, editing) =>
      editing
        ? unwrap(
            await api.PATCH('/api/v1/customers/{customer_id}', {
              params: { path: { customer_id: editing.id } },
              body: values,
            }),
          )
        : unwrap(await api.POST('/api/v1/customers', { body: values })),
  })

  return (
    <Card
      title="Khách hàng & điểm giao"
      extra={
        <Space>
          <Input.Search placeholder="Tìm mã, tên" allowClear onSearch={paging.search} />
          {canEdit && (
            <Button type="primary" onClick={() => modal.show(null)}>
              Thêm khách hàng
            </Button>
          )}
        </Space>
      }
    >
      <Table<Customer>
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data?.items}
        pagination={paging.pagination(query.data?.total)}
        scroll={{ x: 1000 }}
        expandable={{
          expandedRowRender: (c) => (
            <Table<Point>
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={c.delivery_points}
              columns={[
                { title: 'Mã điểm', dataIndex: 'code', width: 100 },
                { title: 'Tên', dataIndex: 'name' },
                { title: 'Địa chỉ', dataIndex: 'address' },
                {
                  title: 'Tọa độ',
                  render: (_, p) => (
                    <a href={mapLink(p.latitude, p.longitude)} target="_blank" rel="noreferrer">
                      {Number(p.latitude).toFixed(5)}, {Number(p.longitude).toFixed(5)}
                    </a>
                  ),
                },
                {
                  title: '',
                  render: (_, p) => (
                    <>
                      {p.is_default && <Tag color="blue">Mặc định</Tag>}
                      {!p.is_active && <Tag>Ngưng</Tag>}
                    </>
                  ),
                },
              ]}
            />
          ),
        }}
        columns={[
          { title: 'Mã KH', dataIndex: 'code', width: 100 },
          { title: 'Tên khách hàng', dataIndex: 'name' },
          { title: 'Điện thoại', dataIndex: 'phone', width: 120 },
          {
            title: 'Yêu cầu xe',
            dataIndex: 'required_vehicle_type',
            width: 100,
            render: (v: Customer['required_vehicle_type']) => VEHICLE_REQUIREMENT[v],
          },
          {
            title: 'Lịch giao',
            width: 160,
            render: (_, c) =>
              [weekdayText(c.delivery_weekdays), c.deliveries_per_week && `${c.deliveries_per_week} lần/tuần`]
                .filter(Boolean)
                .join(' · '),
          },
          { title: 'NV sales', dataIndex: 'sales_rep', width: 140 },
          {
            title: 'Điểm giao',
            width: 90,
            render: (_, c) => c.delivery_points.filter((p) => p.is_active).length,
          },
          {
            title: 'Trạng thái',
            dataIndex: 'is_active',
            width: 110,
            render: (v: boolean) => (v ? <Tag color="green">Hoạt động</Tag> : <Tag>Ngưng</Tag>),
          },
          ...(canEdit
            ? [{ title: '', width: 60, render: (_: unknown, r: Customer) => <a onClick={() => modal.show(r)}>Sửa</a> }]
            : []),
        ]}
      />
      {modal.render(
        (form, editing) => (
          <>
            <Row gutter={12}>
              <Col span={8}>
                <Form.Item name="code" label="Mã KH" rules={[{ required: true }]}>
                  <Input disabled={Boolean(editing)} />
                </Form.Item>
              </Col>
              <Col span={16}>
                <Form.Item name="name" label="Tên khách hàng" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="address" label="Địa chỉ">
              <Input />
            </Form.Item>
            <Row gutter={12}>
              <Col span={8}>
                <Form.Item name="contact_name" label="Người liên hệ">
                  <Input />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="phone" label="Điện thoại">
                  <Input />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="email" label="Email" rules={[{ type: 'email' }]}>
                  <Input />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={12}>
              <Col span={8}>
                <Form.Item name="required_vehicle_type" label="Yêu cầu xe">
                  <Select options={options(VEHICLE_REQUIREMENT)} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="sales_rep" label="NV sales">
                  <Input />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="deliveries_per_week" label="Số lần giao/tuần">
                  <InputNumber min={1} max={7} style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="delivery_weekdays" label="Ngày giao trong tuần">
              <Checkbox.Group options={WEEKDAYS} />
            </Form.Item>
            <Form.Item name="is_active" label="Hoạt động" valuePropName="checked">
              <Switch />
            </Form.Item>

            <Divider titlePlacement="start">Điểm giao</Divider>
            <Form.List name="delivery_points">
              {(fields, { add, remove }) => (
                <>
                  {fields.map((field, index) => (
                    <Card
                      key={field.key}
                      size="small"
                      style={{ marginBottom: 12 }}
                      title={`Điểm giao ${index + 1}`}
                      extra={
                        fields.length > 1 && (
                          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                        )
                      }
                    >
                      <Row gutter={12}>
                        <Col span={8}>
                          <Form.Item name={[field.name, 'code']} label="Mã điểm" rules={[{ required: true }]}>
                            <Input />
                          </Form.Item>
                        </Col>
                        <Col span={16}>
                          <Form.Item name={[field.name, 'name']} label="Tên điểm">
                            <Input />
                          </Form.Item>
                        </Col>
                      </Row>
                      <Form.Item name={[field.name, 'address']} label="Địa chỉ" rules={[{ required: true }]}>
                        <Input />
                      </Form.Item>
                      <CoordinateFields prefix={[field.name]} />
                      <Form.Item name={[field.name, 'is_default']} valuePropName="checked" noStyle>
                        <Checkbox
                          onChange={(e) => {
                            // Chỉ 1 điểm mặc định.
                            if (!e.target.checked) return
                            const points = form.getFieldValue('delivery_points') as Point[]
                            form.setFieldValue(
                              'delivery_points',
                              points.map((p, i) => ({ ...p, is_default: i === field.name })),
                            )
                          }}
                        >
                          Điểm giao mặc định
                        </Checkbox>
                      </Form.Item>
                    </Card>
                  ))}
                  <Button icon={<PlusOutlined />} onClick={() => add({ is_active: true })}>
                    Thêm điểm giao
                  </Button>
                </>
              )}
            </Form.List>
          </>
        ),
        760,
      )}
    </Card>
  )
}
