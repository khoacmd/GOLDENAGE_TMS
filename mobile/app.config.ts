import type { ConfigContext, ExpoConfig } from 'expo/config'

// Cấu hình build APK, thêm vào app.json. URL API được gắn cứng vào bản build qua EXPO_PUBLIC_API_URL.
export default ({ config }: ConfigContext): ExpoConfig => {
  const apiUrl = process.env.EXPO_PUBLIC_API_URL ?? ''
  return {
    ...(config as ExpoConfig),
    plugins: [
      ...(config.plugins ?? []),
      [
        'expo-build-properties',
        {
          android: {
            // Chỉ cho phép HTTP khi máy chủ chưa có HTTPS (pilot trong mạng LAN).
            usesCleartextTraffic: apiUrl.startsWith('http://'),
            // Điện thoại thật đều là ARM; bỏ x86 cho bản build nhẹ và nhanh hơn.
            buildArchs: ['arm64-v8a', 'armeabi-v7a'],
          },
        },
      ],
    ],
  }
}
