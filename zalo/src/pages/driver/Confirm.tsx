import { errorMessage, type components } from '@tms/api-client'
import { useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Box, Button, Header, Input, Page, Spinner, Text, useNavigate, useParams } from 'zmp-ui'

import { api } from '../../lib/api'
import { TEMP_GROUP } from '../../lib/format'
import { locationToken, takePhoto, zaloToken } from '../../lib/zalo'
import { useRules, useTrip } from './useDriver'

type Status = components['schemas']['ItemStatus']

const REASONS = ['Khách vắng nhà / đóng cửa', 'Khách từ chối nhận', 'Sai hàng / thiếu hàng', 'Không liên lạc được khách']
const MAX_PHOTOS = 5

interface Photo {
  key: string
  preview: string
}

/** Xác nhận giao, chỉ online: gửi lỗi mạng thì giữ nguyên `client_id` để gửi lại không bị trùng. */
export function ConfirmPage() {
  const { tripId = '', itemId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const trip = useTrip(tripId)
  const rules = useRules()
  const [status, setStatus] = useState<Extract<Status, 'SUCCESS' | 'FAILED'>>('SUCCESS')
  const [reason, setReason] = useState('')
  const [photos, setPhotos] = useState<Photo[]>([])
  const [uploading, setUploading] = useState(false)
  const [sending, setSending] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const clientId = useRef(crypto.randomUUID())

  const stop = trip.data?.stops.find((s) => s.items.some((i) => i.id === itemId))
  const item = stop?.items.find((i) => i.id === itemId)
  const photoRequired = status === 'SUCCESS' ? rules.data?.photo_required_success : rules.data?.photo_required_failed

  async function addPhoto() {
    setErrors([])
    setUploading(true)
    try {
      const blob = await takePhoto()
      if (!blob) return
      const { data, error } = await api.POST('/api/v1/driver/photos', {
        body: { file: blob } as never,
        bodySerializer: () => {
          const form = new FormData()
          form.append('file', blob, 'chung-tu.jpg')
          return form
        },
      })
      if (!data) return setErrors([errorMessage(error, 'Không tải được ảnh lên')])
      setPhotos((current) => [...current, { key: data.key, preview: URL.createObjectURL(blob) }])
    } catch (e) {
      console.warn('Chụp ảnh lỗi', e)
      setErrors(['Không chụp được ảnh. Hãy cho phép Zalo dùng camera rồi thử lại.'])
    } finally {
      setUploading(false)
    }
  }

  async function submit() {
    setErrors([])
    if (status === 'FAILED' && !reason.trim()) return setErrors(['Chọn hoặc nhập lý do giao không thành công.'])
    if (photoRequired && photos.length === 0) return setErrors(['Cần chụp ảnh chứng từ giao nhận.'])
    setSending(true)
    try {
      let location: { zalo_access_token: string; zalo_location_token: string } | object = {}
      if (rules.data?.confirm_geofence) {
        try {
          location = { zalo_access_token: await zaloToken(), zalo_location_token: await locationToken() }
        } catch (e) {
          console.warn('Lấy vị trí lỗi', e)
          return setErrors(['Cần cho phép chia sẻ vị trí để xác nhận bạn đang ở điểm giao.'])
        }
      }
      const { data, error } = await api.POST('/api/v1/driver/trips/{trip_id}/items/{item_id}/confirm', {
        params: { path: { trip_id: tripId, item_id: itemId } },
        body: {
          client_id: clientId.current,
          status,
          reason: status === 'FAILED' ? reason.trim() : null,
          device_time: new Date().toISOString(),
          is_mock_location: false,
          photo_keys: photos.map((p) => p.key),
          ...location,
        },
      })
      if (!data) return setErrors([errorMessage(error, 'Không gửi được xác nhận')])
      await queryClient.invalidateQueries()
      if (data.accepted) return navigate(-1)
      // Bị từ chối đã được lưu lại; lần xác nhận sau là một thao tác mới.
      clientId.current = crypto.randomUUID()
      setErrors(data.violations)
    } catch (e) {
      console.warn('Gửi xác nhận lỗi', e)
      setErrors(['Không kết nối được máy chủ, vui lòng gửi lại.'])
    } finally {
      setSending(false)
    }
  }

  return (
    <Page className="screen with-header">
      <Header title="Xác nhận giao hàng" />
      {(trip.isLoading || rules.isLoading) && (
        <Box className="center">
          <Spinner />
        </Box>
      )}
      {stop && item && rules.data && (
        <>
          <div className="card">
            <Text bold>{stop.customer_code ? `${stop.customer_code} - ${stop.customer_name}` : stop.name}</Text>
            <Text size="small" className="muted">
              {stop.address}
            </Text>
            <Text size="small">
              {item.external_ref
                ? `Đơn ${item.external_ref} · ${TEMP_GROUP[item.temp_group ?? 'DRY']}`
                : item.description}
            </Text>
          </div>
          <div className="card">
            <Text bold>Kết quả</Text>
            <div className="choice-row">
              <Button
                fullWidth
                variant={status === 'SUCCESS' ? 'primary' : 'secondary'}
                onClick={() => setStatus('SUCCESS')}
              >
                Thành công
              </Button>
              <Button
                fullWidth
                variant={status === 'FAILED' ? 'primary' : 'secondary'}
                type={status === 'FAILED' ? 'danger' : undefined}
                onClick={() => setStatus('FAILED')}
              >
                Không thành công
              </Button>
            </div>
            {status === 'FAILED' && (
              <>
                {REASONS.map((r) => (
                  <button key={r} className={`reason ${reason === r ? 'active' : ''}`} onClick={() => setReason(r)}>
                    {r}
                  </button>
                ))}
                <Input placeholder="Lý do khác" value={reason} onChange={(e) => setReason(e.target.value)} />
              </>
            )}
          </div>
          <div className="card">
            <Text bold>Ảnh chứng từ {photoRequired ? '(bắt buộc)' : '(không bắt buộc)'}</Text>
            {photos.length > 0 && (
              <div className="photos">
                {photos.map((photo) => (
                  <img key={photo.key} src={photo.preview} alt="Chứng từ" />
                ))}
              </div>
            )}
            {photos.length < MAX_PHOTOS && (
              <Button variant="secondary" fullWidth loading={uploading} onClick={() => void addPhoto()}>
                Chụp ảnh
              </Button>
            )}
          </div>
          {rules.data.confirm_geofence && (
            <Text size="small" className="muted notice">
              Vị trí của bạn chỉ dùng để xác nhận đang ở điểm giao (bán kính {rules.data.confirm_radius_m} m) khi gửi.
            </Text>
          )}
          {errors.map((message) => (
            <Text key={message} className="error-text notice">
              {message}
            </Text>
          ))}
          <Box m={3}>
            <Button fullWidth loading={sending} disabled={uploading} onClick={() => void submit()}>
              Gửi xác nhận
            </Button>
          </Box>
        </>
      )}
    </Page>
  )
}
