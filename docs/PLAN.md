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
- [ ] Cấu hình thiết bị (PC/mobile/máy in) - chuyển sang M3 cùng đăng ký thiết bị mobile
- [ ] Quy tắc xác nhận giao (thời gian, bán kính tọa độ) - chuyển sang M3

## M2 – Lập lệnh thủ công & kho
- [x] Kế hoạch ngày, tạo lệnh giao (chuyến) thủ công: chọn xe, kho, đơn hoặc điểm dừng tự do
- [x] Kiểm tra ràng buộc khi lập thủ công (tải trọng, loại hàng, loại xe yêu cầu, kho của xe) + cảnh báo tồn kho
- [x] Phân công lái xe, phụ xe (bắt buộc phụ xe nếu xe yêu cầu)
- [x] Phê duyệt / điều chỉnh / hủy lệnh, audit log
- [x] Thủ kho: danh sách lệnh đã duyệt, phiếu soạn hàng, xác nhận xuất hàng
- [x] In phiếu soạn hàng / phiếu giao hàng (trang in trình duyệt → PDF)
- [x] Quản lý cập nhật thủ công trạng thái đơn, xác nhận kết thúc chuyến
- [x] Bản đồ (MapLibre): chọn tọa độ kho/điểm giao, xem điểm dừng của lệnh
- [ ] Thủ kho giới hạn theo kho được phân công (`user_roles.warehouse_id`)
- [ ] Hoàn trả kho / hủy lệnh sau khi đã xuất kho

## M3 – Mobile cho nhân viên giao hàng (→ pilot vận hành thủ công)
- [ ] Danh sách chuyến được gán, chi tiết điểm dừng, mở chỉ đường
- [ ] Nhận chuyến (DISPATCHED)
- [ ] Xác nhận giao thành công/không thành công + lý do + ảnh chứng từ
- [ ] Server kiểm tra điều kiện thời gian & tọa độ (bán kính dung sai)
- [ ] Hàng đợi offline + đồng bộ idempotent
- [ ] Chuyến tự chuyển "Kết thúc" khi không còn đơn pending, kèm thống kê thành công/thất bại/hủy
- [ ] Quản lý hủy đơn pending trong chuyến (có lý do, audit); đơn thất bại/bị hủy quay về PENDING
- [ ] Pilot với công ty đầu tiên (2 kho, 4 xe)

## M4 – Lập kế hoạch tự động
- [ ] Dựng OSRM (OSM Việt Nam) profile ô tô & xe máy, service ma trận khoảng cách có cache
- [ ] Kiểm tra khả thi từng phần đơn + lý do không xếp được
- [ ] Phân bổ kho theo tồn kho + giữ chỗ tồn
- [ ] Bộ giải OR-Tools: đa kho, đa lượt/xe, tải trọng, ca làm việc, tương thích xe–hàng–khách
- [ ] Bộ dữ liệu benchmark & test cho bộ giải
- [ ] Chạy theo job định kỳ và lệnh manual (worker), lưu `planning_runs`
- [ ] Màn hình xem kế hoạch trên bản đồ, kéo thả điều chỉnh, so sánh chi phí
- [ ] Danh sách đơn không xếp được + cảnh báo

## M5 – Chi phí & báo cáo
- [ ] Ghi nhận km/chi phí thực tế của chuyến
- [ ] Phân bổ chi phí chuyến về đơn theo phương pháp của xe (giá trị đơn/khoảng cách/khối lượng/chuyến)
- [ ] Báo cáo: tỷ lệ giao thành công, đơn giao lại, km, % tải trọng sử dụng, chi phí/đơn, chi phí/kg
- [ ] Xuất Excel

## M6 – Hoàn thiện & mở rộng
- [ ] Kiểm thử bảo mật (cô lập dữ liệu giữa công ty, phân quyền)
- [ ] Build image multi-arch (arm64 + amd64) bằng `docker buildx`
- [ ] Giám sát, backup/restore, triển khai production trên cloud VPS
- [ ] Onboarding công ty thứ 2 (kiểm chứng multi-tenant)
- [ ] (Phase sau) Thể tích / số thùng cho xe & mặt hàng
- [ ] (Phase sau) Đưa lựa chọn kho vào trong bộ giải
- [ ] (Phase sau) Theo dõi vị trí xe thời gian thực
