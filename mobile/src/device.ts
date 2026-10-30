import type { components } from '@tms/api-client'
import { randomUUID } from 'expo-crypto'
import * as SecureStore from 'expo-secure-store'
import { Platform } from 'react-native'

import appConfig from '../app.json'
import { api } from './api'

const ID_KEY = 'tms.installation_id'
let installationId: string | null = null

export type RegisteredDevice = components['schemas']['RegisteredDevice']

/** Mã cài đặt app (sinh 1 lần, mất khi gỡ app) - dùng để đăng ký thiết bị với server. */
export async function getInstallationId(): Promise<string> {
  if (installationId) return installationId
  installationId = await SecureStore.getItemAsync(ID_KEY)
  if (!installationId) {
    installationId = randomUUID()
    await SecureStore.setItemAsync(ID_KEY, installationId)
  }
  return installationId
}

function deviceInfo() {
  const c = Platform.constants as { Brand?: string; Model?: string; Release?: string; osVersion?: string }
  const model = [c.Brand, c.Model].filter(Boolean).join(' ') || undefined
  return {
    platform: Platform.OS,
    model: model?.slice(0, 128),
    os_version: String(c.Release ?? c.osVersion ?? Platform.Version).slice(0, 64),
    app_version: appConfig.expo.version,
  }
}

/** Đăng ký / cập nhật thiết bị; trả trạng thái duyệt (null nếu lỗi mạng). */
export async function registerDevice(): Promise<RegisteredDevice | null> {
  const { data } = await api.POST('/api/v1/driver/device', {
    body: { identifier: await getInstallationId(), ...deviceInfo() },
  })
  return data ?? null
}
