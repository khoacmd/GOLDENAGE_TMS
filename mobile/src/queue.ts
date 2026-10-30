/**
 * Hàng đợi xác nhận giao hàng: ghi xuống máy trước (SQLite), gửi lên server khi có mạng.
 * Mỗi mục có client_id cố định nên gửi lại nhiều lần server chỉ ghi nhận một lần.
 */
import type { components } from '@tms/api-client'
import { randomUUID } from 'expo-crypto'
import { Directory, File, Paths } from 'expo-file-system'
import Storage from 'expo-sqlite/kv-store'

import { API_URL, loadStoredTokens, refreshSession, tokenStore } from './api'

type ConfirmIn = components['schemas']['ConfirmIn']
type ConfirmationOut = components['schemas']['ConfirmationOut']

export interface QueueEntry {
  clientId: string
  tripId: string
  itemId: string
  label: string
  body: Omit<ConfirmIn, 'client_id' | 'photo_keys'>
  photoUris: string[]
  photoKeys: string[]
  state: 'pending' | 'rejected' | 'error'
  messages: string[]
  createdAt: string
}

const KEY = 'tms.confirm-queue'
const PHOTO_DIR = new Directory(Paths.document, 'pending-photos')
const listeners = new Set<() => void>()
let processing: { promise: Promise<void>; since: number; run: number } | null = null
let runCounter = 0
// Một lượt gửi chạy quá lâu coi như bị treo → cho phép lượt mới, tránh kẹt hàng đợi vĩnh viễn.
const STALE_MS = 2 * 60_000
const REQUEST_TIMEOUT_MS = 30_000

function read(): QueueEntry[] {
  const raw = Storage.getItemSync(KEY)
  return raw ? (JSON.parse(raw) as QueueEntry[]) : []
}

function write(entries: QueueEntry[]) {
  Storage.setItemSync(KEY, JSON.stringify(entries))
  listeners.forEach((l) => l())
}

export const getQueue = read

export function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Chép ảnh từ cache của camera sang thư mục của app để không bị hệ điều hành dọn mất. */
function persistPhoto(uri: string): string {
  if (!PHOTO_DIR.exists) PHOTO_DIR.create({ intermediates: true })
  const target = new File(PHOTO_DIR, `${randomUUID()}.jpg`)
  new File(uri).copy(target)
  return target.uri
}

function removePhotos(uris: string[]) {
  for (const uri of uris) {
    const file = new File(uri)
    if (file.exists) file.delete()
  }
}

export function enqueue(entry: Omit<QueueEntry, 'clientId' | 'photoKeys' | 'state' | 'messages' | 'createdAt'>) {
  const item: QueueEntry = {
    ...entry,
    clientId: randomUUID(),
    photoUris: entry.photoUris.map(persistPhoto),
    photoKeys: [],
    state: 'pending',
    messages: [],
    createdAt: new Date().toISOString(),
  }
  write([...read(), item])
  void processQueue()
}

/** Gửi lại mục bị lỗi kỹ thuật (không phải bị từ chối do vi phạm quy tắc). */
export function retry(clientId: string) {
  update(clientId, { state: 'pending', messages: [] })
  void processQueue()
}

export function discard(clientId: string) {
  const entry = read().find((e) => e.clientId === clientId)
  if (entry) removePhotos(entry.photoUris)
  write(read().filter((e) => e.clientId !== clientId))
}

function update(clientId: string, patch: Partial<QueueEntry>) {
  write(read().map((e) => (e.clientId === clientId ? { ...e, ...patch } : e)))
}

class NetworkError extends Error {}

/** Gọi API kèm token; hết hạn (401) thì làm mới token và thử lại một lần. */
async function request(path: string, init: RequestInit): Promise<Response> {
  // Hàng đợi có thể chạy ngay khi mở app, trước khi màn hình nạp token từ SecureStore.
  if (!tokenStore.get()) await loadStoredTokens()
  if (!tokenStore.get()) throw new NetworkError('Chưa đăng nhập')
  const resp = await rawRequest(path, init)
  if (resp.status !== 401 || !(await refreshSession().catch(() => false))) return resp
  return rawRequest(path, init)
}

async function rawRequest(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()?.access_token
  if (token) headers.set('Authorization', `Bearer ${token}`)
  // Mạng chập chờn có thể làm request treo mà không lỗi (fetch của Expo không luôn tôn trọng
  // abort) → tự hẹn giờ bằng Promise.race để hàng đợi đi tiếp và thử lại lượt sau.
  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout> | undefined
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      controller.abort()
      reject(new Error('Hết thời gian chờ máy chủ'))
    }, REQUEST_TIMEOUT_MS)
  })
  try {
    return await Promise.race([fetch(`${API_URL}${path}`, { ...init, headers, signal: controller.signal }), timeout])
  } catch (e) {
    console.warn('Gửi xác nhận thất bại, sẽ thử lại', path, e)
    throw new NetworkError('Không có kết nối mạng')
  } finally {
    clearTimeout(timer)
  }
}

async function errorText(resp: Response) {
  const body = (await resp.json().catch(() => null)) as { error?: { message?: string } } | null
  return body?.error?.message ?? `Lỗi máy chủ (${resp.status})`
}

async function send(entry: QueueEntry): Promise<void> {
  const keys = [...entry.photoKeys]
  for (const uri of entry.photoUris.slice(keys.length)) {
    const form = new FormData()
    // fetch của Expo nhận File (expo-file-system, triển khai Blob), không nhận {uri, name, type}.
    form.append('file', new File(uri), 'chung-tu.jpg')
    const resp = await request('/api/v1/driver/photos', { method: 'POST', body: form })
    if (!resp.ok) throw new Error(await errorText(resp))
    keys.push(((await resp.json()) as { key: string }).key)
    update(entry.clientId, { photoKeys: keys }) // ảnh đã lên không phải tải lại
  }
  const resp = await request(`/api/v1/driver/trips/${entry.tripId}/items/${entry.itemId}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...entry.body, client_id: entry.clientId, photo_keys: keys }),
  })
  if (resp.status === 401) throw new NetworkError('Phiên đăng nhập hết hạn')
  if (!resp.ok) {
    update(entry.clientId, { state: 'error', messages: [await errorText(resp)] })
    return
  }
  const result = (await resp.json()) as ConfirmationOut
  if (result.accepted) {
    removePhotos(entry.photoUris)
    write(read().filter((e) => e.clientId !== entry.clientId))
  } else {
    update(entry.clientId, { state: 'rejected', messages: result.violations })
  }
}

/** Gửi các mục đang chờ theo thứ tự; dừng khi mất mạng (sẽ thử lại sau). */
export function processQueue(): Promise<void> {
  if (processing && Date.now() - processing.since < STALE_MS) return processing.promise
  const run = ++runCounter
  const promise = (async () => {
    try {
      for (const entry of read().filter((e) => e.state === 'pending')) {
        try {
          await send(entry)
        } catch (e) {
          if (e instanceof NetworkError) break
          update(entry.clientId, { state: 'error', messages: [(e as Error).message] })
        }
      }
    } finally {
      if (processing?.run === run) processing = null
    }
  })()
  processing = { promise, since: Date.now(), run }
  return promise
}
