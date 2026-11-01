# Kế hoạch phát triển

> Tham chiếu kiến trúc: [ARCHITECTURE.md](ARCHITECTURE.md). Đánh dấu `- [x]` khi hoàn thành.

## M0 – Nền tảng
- [x] Phân tích nghiệp vụ, chốt kiến trúc & tech stack (docs/ARCHITECTURE.md)
- [x] Xác nhận các giả định D9–D13
- [x] Xác nhận giả định D14 (item bị hủy khỏi chuyến quay về pool)
- [x] Khởi tạo git repo, cấu trúc monorepo (`backend/`, `web/`, `mobile/`, `packages/`, `infra/`)
- [x] Backend: FastAPI skeleton, cấu hình, `uv`, `ruff`, `mypy`, `pytest`
- [x] Cài `uv`, `pnpm` trên máy Spark
- [x] Docker Compose dev (arm64): PostgreSQL+PostGIS (`imresamu/postgis`), Redis, SeaweedFS S3
- [x] Kiểm chứng môi trường giả lập mobile trên ARM64: Redroid (Android 14 arm64) + Expo Go, xem `infra/android/README.md`
- [x] Đẩy repo lên remote (GitHub) để CI chạy
- [x] Alembic + cơ chế tenancy (`company_id`, RLS, tenant context per request/job)
- [x] Auth JWT + refresh token, RBAC 5 vai trò
- [x] Web skeleton (Vite + React + Ant Design), đăng nhập, layout theo vai trò
- [x] Mobile skeleton (Expo), đăng nhập
- [x] Sinh TS API client từ OpenAPI
- [x] CI: lint, type-check, test cho backend/web/mobile
- [x] Cập nhật mục "Lệnh phát triển" trong CLAUDE.md

## M1 – Dữ liệu gốc & tích hợp
- [x] System admin: mở/đóng công ty, gán company admin (API + web)
- [x] Company admin: user, vai trò (tài khoản thuộc `home_company_id`)
- [x] Cấu hình công ty: ngày làm việc, giờ ca, cut-over, múi giờ
- [x] CRUD kho (nhập tọa độ, link xem bản đồ OSM)
- [x] CRUD đội xe + gán kho được phép lấy hàng
- [x] Khách hàng & điểm giao (import + chỉnh sửa, 1 điểm mặc định)
- [x] Mặt hàng: import file / API
- [x] Đơn hàng: import file / API, tự tách `order_parts` DRY/COLD, phân bổ giá trị, khóa khi đã vào kế hoạch, quản lý hủy đơn
- [x] Tồn kho: import file / API (snapshot theo kho), màn hình xem tồn
- [x] Báo cáo lỗi import theo dòng, upsert idempotent, all-or-nothing, dry-run, lịch sử import
- [x] Template chuẩn 6 loại dữ liệu + `docs/IMPORT_TEMPLATES.md` (sinh tự động) + dữ liệu mẫu `docs/samples/`
- [x] API key cho hệ thống ngoài (`/api/v1/integration/{loại}`)
- [x] Bản đồ: chọn tọa độ trên bản đồ (làm ở M2)
- [x] Cấu hình thiết bị (PC/mobile/máy in) - làm ở M3 cùng đăng ký thiết bị mobile
- [x] Quy tắc xác nhận giao (thời gian, bán kính tọa độ) - làm ở M3

## M2 – Lập lệnh thủ công & kho
- [x] Kế hoạch ngày, tạo lệnh giao (chuyến) thủ công: chọn xe, kho, đơn hoặc điểm dừng tự do
- [x] Kiểm tra ràng buộc khi lập thủ công (tải trọng, loại hàng, loại xe yêu cầu, kho của xe) + cảnh báo tồn kho
- [x] Phân công lái xe, phụ xe (bắt buộc phụ xe nếu xe yêu cầu)
- [x] Phê duyệt / điều chỉnh / hủy lệnh, audit log
- [x] Thủ kho: danh sách lệnh đã duyệt, phiếu soạn hàng, xác nhận xuất hàng
- [x] Bổ sung trạng thái "Đã soạn hàng" (`PREPARED`) giữa "Đã duyệt" và "Đã xuất kho": nút "Xác nhận soạn hàng" ở màn hình Xuất kho và chi tiết lệnh, lọc "Cần xử lý"
- [x] In phiếu soạn hàng / phiếu giao hàng (trang in trình duyệt → PDF)
- [x] Quản lý cập nhật thủ công trạng thái đơn, xác nhận kết thúc chuyến
- [x] Bản đồ (MapLibre): chọn tọa độ kho/điểm giao, xem điểm dừng của lệnh
- [ ] (Phase sau) Thủ kho giới hạn theo kho được phân công (`user_roles.warehouse_id`)
- [ ] (Phase sau) Hoàn trả kho / hủy lệnh sau khi đã xuất kho

## M3 – Mobile cho nhân viên giao hàng (→ pilot vận hành thủ công)
- [x] Danh sách chuyến được gán, chi tiết điểm dừng, mở chỉ đường (Google Maps)
- [x] Nhận hàng & xuất phát (DISPATCHED)
- [x] Xác nhận giao thành công/không thành công + lý do + ảnh chứng từ (S3/SeaweedFS)
- [x] Server kiểm tra điều kiện thời gian & tọa độ (bán kính dung sai), ảnh bắt buộc, vị trí giả lập, độ trễ offline
- [x] Hàng đợi offline (SQLite + ảnh lưu trong app) + đồng bộ idempotent (client_id), tự làm mới token
- [x] Chuyến tự chuyển "Kết thúc" khi không còn đơn pending, kèm thống kê thành công/thất bại/hủy
- [x] Quản lý hủy đơn pending trong chuyến (có lý do, audit); đơn thất bại/bị hủy quay về PENDING
- [x] Web: cấu hình quy tắc xác nhận giao; xem lịch sử xác nhận + ảnh trong chi tiết chuyến
- [x] Định vị dự phòng khi máy không có Google Play Services: module native `mobile/modules/tms-location` (LocationManager), chỉ có trong bản APK
- [x] Workflow build APK trên GitHub Actions x86-64 (`.github/workflows/mobile-apk.yml`, chạy tay, nhập URL API)
- [x] Đăng nhập app bằng mã PIN 6 số do admin công ty đặt (chỉ tài khoản lái xe; trang Người dùng: đặt/đổi/xóa PIN)
- [ ] Kiểm tra APK trên điện thoại thật (GPS dự phòng, camera, mở chỉ đường Google Maps); keystore phát hành riêng
- [ ] (Cải tiến) Mở chỉ đường: ưu tiên `google.navigation:` (Google Maps dẫn đường) → `geo:` (ứng dụng bản đồ khác) → link web; không mở được thì báo lỗi kèm tọa độ (hiện `Linking.openURL` lỗi bị bỏ qua im lặng). Giả lập Redroid không có Google Maps/trình duyệt thật nên chỉ đường không chạy được ở đó (`ERR_UNKNOWN_URL_SCHEME`), không phải lỗi app
- [x] Thiết bị: admin quản lý PC/máy in, điện thoại tự đăng ký khi mở app, tùy chọn bắt buộc duyệt, khóa máy → từ chối xác nhận giao
- [x] Bản đồ tự host trên web: PMTiles + style Protomaps (tiếng Việt), service `tiles` (nginx), tự quay về tile OSM nếu chưa có dữ liệu
- [x] Tải dữ liệu bản đồ Việt Nam (zoom 0–14, 638 MB) và kiểm tra hiển thị
- [ ] Pilot với công ty đầu tiên (2 kho, 4 xe)

## M4 – Lập kế hoạch tự động
- [x] Service ma trận khoảng cách: OSRM `/table` + cache Redis, dự phòng ước lượng đường chim bay
- [x] OSRM: script `infra/osrm/prepare-vietnam.sh` (profile ô tô + xe máy), service `osrm-car`/`osrm-motorbike` (compose profile `routing`)
- [x] Dữ liệu OSRM Việt Nam đã dựng xong (ô tô + xe máy), bật `TMS_OSRM_*_URL` và so sánh với ước lượng (quãng đường +5,6%; thời gian nhân hệ số kẹt xe cấu hình theo công ty, D28)
- [x] Kiểm tra khả thi từng phần đơn + lý do không xếp được
- [x] Phân bổ kho theo tồn kho (giữ chỗ = lệnh chưa xuất kho)
- [x] Bộ giải OR-Tools: đa kho, đa lượt/xe, tải trọng, ca làm việc, tương thích xe–hàng–khách
- [x] Bộ dữ liệu benchmark & test cho bộ giải (100 điểm, 2 kho, 4 xe)
- [x] Chạy theo job định kỳ (cut-over → ngày làm việc kế tiếp) và lệnh manual (worker Dramatiq), lưu `planning_runs`
- [x] Màn hình xem kế hoạch trên bản đồ, kéo thả điều chỉnh, so sánh chi phí
- [x] Danh sách đơn không xếp được + cảnh báo
- [x] Sửa: phần đơn giao thất bại xếp lại được vào lệnh mới (D25)
- [x] Vẽ tuyến theo đường thực tế (OSRM `/route`) thay cho đường thẳng trên bản đồ
- [x] Đưa worker + scheduler vào Docker Compose / triển khai (cùng M6, `infra/prod`)
- [ ] (Khi có dữ liệu) Hiệu chỉnh hệ số thời gian di chuyển theo giờ xuất phát/kết thúc thực tế của chuyến

## M5 – Chi phí & báo cáo
- [x] Ghi nhận km/chi phí thực tế của chuyến (công-tơ-mét / số km / km kế hoạch / ước lượng + chi phí phát sinh), tự ghi nhận khi kết thúc chuyến
- [x] Phân bổ chi phí chuyến về đơn theo phương pháp của xe (giá trị đơn/khoảng cách/khối lượng/chuyến)
- [x] Báo cáo: tỷ lệ giao thành công, đơn giao lại, km, % tải trọng sử dụng, chi phí/đơn, chi phí/kg; theo xe/ngày/khách hàng/lý do thất bại
- [x] Xuất Excel (6 sheet, gồm chi tiết từng đơn)
- [ ] (Tùy chọn) Lái xe nhập số công-tơ-mét lúc xuất phát / kết thúc trên app mobile
- [ ] (Tùy chọn) Biểu đồ xu hướng theo ngày trên trang báo cáo

## M6 – Hoàn thiện & mở rộng
- [x] Kiểm thử bảo mật (cô lập dữ liệu giữa công ty, phân quyền): quét tự động mọi endpoint (`tests/test_security.py`)
- [x] Vá sau kiểm thử: lái xe không xem được lịch sử/template import; lịch sử & xác nhận của lệnh công ty khác trả 404; chống dò mật khẩu (429); giới hạn kích thước file import
- [x] Build image multi-arch (arm64 + amd64): `backend/Dockerfile`, `web/Dockerfile`, workflow Images → GHCR
- [x] Bộ triển khai production `infra/prod` (Caddy HTTPS, nginx, api/worker/scheduler/migrate, OSRM tùy chọn), chạy thử đầy đủ trên máy arm64
- [x] Giám sát: `/health` + healthcheck, log JSON, Sentry tùy chọn; backup/restore (đã diễn tập khôi phục)
- [x] Hướng dẫn triển khai, cập nhật, onboarding: `docs/DEPLOY.md`
- [x] Triển khai production trên máy Spark (Docker Compose, `DATA_DIR=/home/khoanx/tms-prod`, OSRM + bản đồ), public qua Cloudflare Tunnel (service `cloudflared`, profile `tunnel`; Caddy lấy IP thật từ `CF-Connecting-IP`)
- [x] Gắn tên miền `tms.thanhxuan.me` + token Cloudflare Tunnel; cron backup 2h sáng hằng ngày
- [x] Build APK với URL production (`https://tms.thanhxuan.me`, workflow Mobile APK, 01/11/2026)
- [x] Tạo tài khoản admin hệ thống trên production (`systemadmin`, 01/11/2026)
- [ ] Đồng bộ backup ra ngoài máy
- [ ] (Khi cần) Chuyển sang cloud VPS: cùng bộ `infra/prod`, khôi phục từ backup
- [x] Người dùng tự đổi mật khẩu trên web và mobile (`POST /auth/change-password`); đổi/đặt lại mật khẩu đăng xuất các phiên khác (D31)
- [x] Vá lỗi đăng xuất không kết thúc phiên: web/mobile về màn hình đăng nhập ngay, server thu hồi token của phiên (`POST /auth/logout`), đồng bộ đăng xuất giữa các tab
- [x] Đưa tính năng đổi mật khẩu + vá đăng xuất lên production (`864ebcc`, có migration), build lại APK (`1.0.0-3`)
- [x] Kiểm chứng multi-tenant trên stack production: 2 công ty cùng dữ liệu mẫu, lập kế hoạch song song, cô lập dữ liệu
- [ ] Onboarding công ty thứ 2 thật (quy trình: `docs/DEPLOY.md` mục 7)
- [ ] (Phase sau) Thể tích / số thùng cho xe & mặt hàng
- [ ] (Phase sau) Đưa lựa chọn kho vào trong bộ giải
- [ ] (Phase sau) Theo dõi vị trí xe thời gian thực

## M7 – Zalo Mini App (khách hàng + tài xế kênh phụ)
- [ ] Đăng ký Zalo OA doanh nghiệp (công ty vận hành TMS đứng tên) + tạo Zalo Mini App, xin quyền SĐT/vị trí, khai báo domain API `tms.thanhxuan.me`
- [x] Chốt yêu cầu, kiến trúc, phương án mã kích hoạt (D32–D35, ARCHITECTURE mục 11b)
- [x] Liên hệ khách hàng: bảng `customer_contacts` (chủ / điểm giao, SĐT chuẩn hóa), web thêm/sửa/xóa (Khách hàng → Liên hệ), loại import "Liên hệ khách hàng" + mẫu `docs/samples/7-lien-he-khach-hang.csv`
- [x] Mã kích hoạt: tạo / tạo lại / thu hồi cho liên hệ khách và tài xế, link + QR, chống dò, audit (web: Khách hàng → Liên hệ, Người dùng; Cấu hình → hạn mã); nhập mã `zalo.service.redeem` (endpoint ở bước xác thực Zalo)
- [x] Xác thực Zalo (`POST /auth/zalo/login|activate|refresh`), liên kết bằng mã, chọn tài khoản (công ty / lái xe / khách hàng), JWT khách hàng (`customer_*`), `GET /customer/me`; chế độ giả lập `TMS_ZALO_MOCK`; test bảo mật cho token khách
- [ ] Kiểm chứng gọi Graph API của Zalo (`appsecret_proof`) với App ID/secret thật
- [ ] API khách hàng: đơn theo ngày, chi tiết + log giao (ảnh chứng từ), phân quyền chủ/điểm giao, ẩn giá trị với điểm giao
- [ ] Giờ đến dự kiến: `trip_stops.planned_arrival` + tính lại theo giờ giao thực tế
- [ ] Tuyến đã đi (OSRM, không lộ điểm dừng khác); SĐT/Zalo tài xế khi chuyến đang giao
- [ ] Mini app `zalo/` (React + ZaUI + zmp-sdk): phần khách hàng; `packages/api-client` cho chọn đường dẫn làm mới token (`/auth/zalo/refresh`); CORS cho domain của Zalo Mini App
- [ ] Mini app: phần tài xế (kênh phụ), cấu hình công ty "cho phép xác nhận giao qua Zalo"
- [ ] Kiểm thử trên Zalo thật, gửi duyệt và phát hành mini app
