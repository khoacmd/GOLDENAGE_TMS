import { chooseImage, getAccessToken, getLocation, openPhone, openWebview } from 'zmp-sdk'

/** Dev trên trình duyệt (không có Zalo): token giả, backend bật TMS_ZALO_MOCK. */
function mockToken(): string | null {
  if (!import.meta.env.DEV) return null
  return localStorage.getItem('tms-mock-token') ?? 'mock:zalo-dev:Khách thử'
}

export async function zaloToken(): Promise<string> {
  return mockToken() ?? (await getAccessToken())
}

export function callPhone(phone: string) {
  if (import.meta.env.DEV) window.open(`tel:${phone}`)
  else void openPhone({ phoneNumber: phone })
}

/** Zalo của tài xế = số điện thoại (Zalo ID theo ứng dụng không dùng để nhắn được). */
export function openZalo(phone: string) {
  const url = `https://zalo.me/${phone}`
  if (import.meta.env.DEV) window.open(url)
  else void openWebview({ url })
}

/** Mở chỉ đường (Google Maps) ngoài mini app. */
export function openDirections(latitude: string | number, longitude: string | number) {
  const url = `https://www.google.com/maps/dir/?api=1&destination=${latitude},${longitude}`
  if (import.meta.env.DEV) window.open(url)
  else void openWebview({ url })
}

/** Token vị trí dùng 1 lần (hạn 2 phút): server đổi lấy tọa độ qua Zalo. */
export async function locationToken(): Promise<string> {
  if (import.meta.env.DEV) return localStorage.getItem('tms-mock-location') ?? 'mock:21,105'
  const { token } = await getLocation({})
  if (!token) throw new Error('Không lấy được vị trí')
  return token
}

/** Thu nhỏ ảnh chụp trước khi tải lên (giới hạn server 8 MB, mạng di động). */
async function shrink(blob: Blob, maxSide = 1600): Promise<Blob> {
  const bitmap = await createImageBitmap(blob)
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  return new Promise((resolve) => canvas.toBlob((out) => resolve(out ?? blob), 'image/jpeg', 0.7))
}

/** Chụp ảnh chứng từ (dev: chọn file). Trả null nếu người dùng bỏ qua. */
export async function takePhoto(): Promise<Blob | null> {
  if (import.meta.env.DEV) {
    return new Promise((resolve) => {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = 'image/*'
      input.dataset.testid = 'dev-photo'
      input.style.display = 'none'
      input.onchange = () => resolve(input.files?.[0] ?? null)
      document.body.append(input)
      input.click()
    }).then((file) => (file ? shrink(file as Blob) : null))
  }
  const { filePaths } = await chooseImage({ sourceType: ['camera'], cameraType: 'back', count: 1 })
  if (!filePaths[0]) return null
  const response = await fetch(filePaths[0])
  return shrink(await response.blob())
}
