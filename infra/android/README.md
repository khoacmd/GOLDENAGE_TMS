# Giả lập Android (Redroid) trên máy dev ARM64

1. Nạp module binder (mỗi lần khởi động máy, hoặc cấu hình `/etc/modules-load.d`):
   `sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"`
2. Chạy giả lập + adb server: `docker compose -f infra/docker-compose.yml --profile mobile up -d redroid adb`
3. Kết nối: `infra/android/adb.sh connect localhost:5555`
4. Cài Expo Go đúng SDK (lần đầu): URL APK lấy từ
   `curl -s https://api.expo.dev/v2/versions/latest` → `sdkVersions["58.0.0"].androidClientUrl`,
   tải về rồi `docker run --rm -i --network host -v <thư-mục-apk>:/apk:ro tms-adb -s localhost:5555 install -r /apk/<file>.apk`
5. Chạy backend (`--host 0.0.0.0`) và Metro:
   `cd mobile && EXPO_PUBLIC_API_URL=http://172.17.0.1:8000 REACT_NATIVE_PACKAGER_HOSTNAME=172.17.0.1 pnpm start`
   (172.17.0.1 = gateway Docker, địa chỉ của máy host nhìn từ Redroid)
6. Mở app: `infra/android/adb.sh -s localhost:5555 shell am start -a android.intent.action.VIEW -d exp://172.17.0.1:8081`
7. Chụp màn hình: `infra/android/adb.sh -s localhost:5555 exec-out screencap -p > screen.png`

Lưu ý: không chạy Metro với `CI=1` khi cần fast refresh/log từ app.
