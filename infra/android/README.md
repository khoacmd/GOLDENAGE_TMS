# Giả lập Android (Redroid) trên máy dev ARM64

1. Nạp module binder (mỗi lần khởi động máy, hoặc cấu hình `/etc/modules-load.d`):
   `sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"`
2. Chạy giả lập + adb server: `docker compose -f infra/docker-compose.yml --profile mobile up -d redroid adb`
3. Kết nối: `infra/android/adb.sh connect localhost:5555`
4. Cài Expo Go đúng SDK (lần đầu): URL APK lấy từ
   `curl -s https://api.expo.dev/v2/versions/latest` → `sdkVersions["58.0.0"].androidClientUrl`,
   tải về rồi `docker run --rm -i --network host -v <thư-mục-apk>:/apk:ro tms-adb -s localhost:5555 install -r /apk/<file>.apk`
5. Cho Android gọi `localhost` của máy host (không phụ thuộc IP mạng Docker):
   `infra/android/adb.sh -s localhost:5555 reverse tcp:8081 tcp:8081` và `... reverse tcp:8000 tcp:8000`
6. Chạy backend và Metro: `cd mobile && EXPO_PUBLIC_API_URL=http://localhost:8000 pnpm start --localhost`
7. Mở app: `infra/android/adb.sh -s localhost:5555 shell am start -a android.intent.action.VIEW -d exp://localhost:8081`
8. Chụp màn hình: `infra/android/adb.sh -s localhost:5555 exec-out screencap -p > screen.png`

Lưu ý:
- Không chạy Metro với `CI=1` khi cần fast refresh/log từ app. Sau khi sửa module không phải component (vd. `src/queue.ts`), nên khởi động lại app (`am force-stop host.exp.exponent`) để tránh 2 bản module cùng tồn tại.
- Redroid **không có Google Play Services** → `expo-location` không lấy được vị trí. Để test luồng xác nhận giao, tạm tắt "Kiểm tra vị trí" ở màn hình Cấu hình (logic vị trí đã có test backend).
- Redroid không có camera → bản dev có nút "Chọn ảnh có sẵn". Đưa ảnh vào máy: `adb push anh.png /sdcard/Pictures/` rồi
  `adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Pictures/anh.png`.
- Giả lập mất mạng tới server: `adb reverse --remove tcp:8000`, nối lại: `adb reverse tcp:8000 tcp:8000`.
