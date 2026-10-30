
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Nguyên tắc giao tiếp
- Luôn bắt đầu mỗi câu trả lời bằng `[Claude]`.
- Luôn sử dụng tiếng Việt có dấu.

## Trạng thái dự án
- Đã chốt kiến trúc & tech stack (FastAPI + PostgreSQL/PostGIS + OR-Tools + OSRM; web React/TS; mobile React Native/Expo) trong `docs/ARCHITECTURE.md`. Lộ trình trong `docs/PLAN.md`.
- Đang ở M0 (nền tảng): đã có backend (tenancy/RLS, auth, RBAC), web & mobile skeleton, CI.
- Tài liệu yêu cầu gốc: `Mô tả yêu cầu1.odt`. Phần "Nghiệp vụ" bên dưới là bản mới hơn, ưu tiên dùng bản này.

## Lệnh phát triển
- Monorepo: `backend/` (Python, uv), `web/` + `mobile/` + `packages/api-client/` (pnpm workspace), `infra/` (Docker Compose).
- Công cụ: `uv`, `pnpm` (trong `~/.local/bin`). `.venv` ở thư mục gốc là di sản PyCharm, không dùng; backend có `.venv` riêng do uv quản lý (nếu shell đang activate `.venv` gốc, chạy `unset VIRTUAL_ENV` để tắt cảnh báo của uv).
- Hạ tầng dev: `docker compose -f infra/docker-compose.yml up -d` (Postgres :55432, Redis :56379, S3 SeaweedFS :58333). Database `tms` (dev) và `tms_test` (test).
- Backend (chạy trong `backend/`):
  - Cài đặt: `uv sync`; migration: `uv run alembic upgrade head`; tạo migration: `uv run alembic revision --autogenerate -m "..."`
  - Chạy API: `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
  - Kiểm tra: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`
  - Chạy 1 test: `uv run pytest tests/test_auth.py::test_refresh_token`
  - Tạo admin hệ thống: `uv run python -m app.cli create-system-admin --username sysadmin`
- Frontend (chạy ở thư mục gốc): `pnpm install`; `pnpm web:dev` (http://localhost:5173, proxy `/api` → :8000); `pnpm typecheck`; `pnpm lint`.
- Dữ liệu demo: import lần lượt các file trong `docs/samples/` ở màn hình Import dữ liệu (đăng nhập `demo_admin`).
- Sau mỗi lần đổi API backend: `pnpm api:generate` (sinh lại `packages/api-client/src/schema.d.ts`, CI kiểm tra file này khớp).
- Mobile: `cd mobile && EXPO_PUBLIC_API_URL=http://<ip-máy>:8000 pnpm start`. Giả lập Android trên Spark (Redroid + Expo Go): xem `infra/android/README.md`.
- `packages/api-client`: middleware của openapi-fetch phải trả `undefined` khi không thay request/response (React Native từ chối object Response gốc).
- Máy dev/test là DGX Spark **ARM64 (aarch64)**: mọi Docker image phải hỗ trợ `linux/arm64`. Production chạy trên cloud VPS.
- Quy ước code backend:
  - Bảng theo công ty dùng `TenantMixin`; migration tạo bảng đó PHẢI gọi `enable_tenant_rls()` (`app/core/rls.py`). Test `test_every_tenant_table_has_forced_rls` sẽ fail nếu quên.
  - API dùng role DB `tms_app` (chịu RLS); context công ty đặt qua `set_tenant_context`, tự áp lại sau mỗi commit.
  - Route ghi dữ liệu tự gọi `await session.commit()`; service chỉ `flush()`.
  - Lỗi nghiệp vụ raise `AppError` và các lớp con (`app/core/errors.py`).
  - Danh sách trả `Page[T]` (`app/core/schemas.py`), tham số `q/limit/offset` qua `page_params`.
  - Thêm/sửa loại import: khai báo `ImportSpec` ở module sở hữu dữ liệu, đăng ký trong `integration/registry.py`, rồi chạy `uv run python -m app.cli export-import-docs ../docs/IMPORT_TEMPLATES.md` (CI kiểm tra file này khớp code). Dữ liệu mẫu `docs/samples/` phải luôn import được (có test).
- Quy ước code web: gọi API qua `api` (openapi-fetch) + `unwrap()`; bảng phân trang dùng `usePaging()`; form tạo/sửa dùng `useEntityModal()` (`web/src/lib/`); nhãn tiếng Việt cho enum ở `web/src/lib/labels.ts`. antd 6: dùng `orientation` thay `direction`.

## Nghiệp vụ
- Nghiệp vụ này được thiết kế chung cho nhiều Công ty cùng sử dụng chung hệ thống.
- Phầm mềm quản lý các đơn hàng cần xử lý giao hàng hàng ngày. Các đơn hàng này được load hoặc tích hợp với hệ thống quản lý đơn bán hàng (chạy độc lập). Trên đơn có thông tin về khách hàng, điểm giao,mặt hàng và số lượng từng mặt hàng, giá trị đơn hàng, ngày yêu cầu giao hàng
- Thông tin khách hàng:
  + Mã
  + Tên
  + Địa chỉ
  + Thông tin liên lạc
  + Các điểm giao (một khách hàng có thể có nhiều điểm giao):
    * Địa chỉ
    * Tọa độ: lattitude/longtitude
  + Tần suất giao hàng (các ngày trong tuần/số lần giao theo tuần)
  + Yêu cầu về phương tiện vận chuyển: ô tô/xe máy
  + Nhân viên sales phụ trách.
- Thông tin kho hàng:
  + Mã Kho
  + Tên Kho
  + Địa chỉ
  + Tọa độ
- Đội xe giao hàng:
  + Mã xe
  + Tên xe
  + Yêu cầu phụ xe: có/không
  + Biển số xe
  + Loại xe: Ô tô/ Xe máy
  + Trọng tải (kg)
  + Chi phí ước tính cho mỗi km di chuyển
  + Loại hàng ưu tiên: chỉ hàng khô/ chỉ hàng đông lạnh/ không phân biệt
  + Các kho có thể lấy hàng: một hoặc nhiều điểm kho (chỉ định đích danh các kho được gán)
  + Phương pháp ghi nhận chi phí: giá trị đơn hàng/tổng khoảng cách/khối lượng hàng/chuyến hàng
- Thông tin mặt hàng: load hoặc tích hợp từ hệ thống bán hàng (chạy độc lập)
  + Mã
  + Tên
  + Loại: hàng khô/ hàng lạnh/hàng đông
  + Đơn vị
  + Trọng lượng
- Thông tin chuyến giao:
  + Mã xe
  + Lái xe
  + Phụ xe
  + Danh sách đơn hàng được giao trong chuyến
  + Tình trạng chuyến: chưa giao/đang giao/kết thúc. Chuyến chỉ "kết thúc" khi không còn đơn pending (mỗi đơn đã giao thành công, không thành công hoặc bị hủy), kèm thống kê thành công/thất bại. Chỉ quản lý mới được hủy đơn đang pending.
- Thông tin giao hàng:
  + Xác nhận trạng thái: đã giao thành công/không giao hàng thành công
  + Thời gian giao (tự động ghi nhận tại thời điểm cập nhật, có thể chỉnh sửa)
  + Hình ảnh chứng từ giao nhận (chụp ảnh giấy giao hàng)
- Ca giao hàng:
  + Việc giao hàng được thực hiện trong các ngày từ thứ 2 đến thứ 7 hàng tuần
  + Giờ làm việc từ 7h đến 19h
  + Quy định này có thể cấu hình linh hoạt theo thực tế.
- Kế hoạch giao hàng: được xây dựng dựa trên nguyên tắc thực hiện
  + Kế hoạch giao hàng của mỗi ngày là tập hợp của các lệnh giao hàng được lập trong ngày
  + Lệnh giao hàng có thể được lập tự động hoặc thủ công 
  + Việc lập Kế hoạch giao hàng tự động đảm bảo 100% số đơn yêu cầu được giao trong ngày (tính đến thời điểm cut-over) bao gồm cả các đơn chưa giao thành công trước đó.
  + Kế hoạch tự động có thể được sinh theo job định kỳ hoặc lệnh manual
  + Lệnh giao được gán cho từng chuyến giao, mỗi lệnh tương ứng với 1 chuyến.
  + Lệnh giao hàng thủ công có thể được lập mà không cần dựa vào thông tin đơn hàng.
  + Đơn hàng gán cho lệnh giao đảm bảo đáp ứng yêu cầu giao theo đơn, tối thiểu hóa số lần giao để hoàn thành đơn, tối ưu cung đường, trọng lượng vận chuyển và chi phí.
  + Một xe vận chuyển có thể thực hiện nhiều lươt, mỗi lượt 1 lệnh trong thời gian được quy định bởi ca làm việc.
- Quản lý kho hàng:
  + Hàng tồn kho được tích hợp từ hệ thống bên ngoài, chạy độc lập, thông qua API hoặc upload file.
- Phân quyền:
  + admin hệ thống quản lý viêc cấu hình thiết lập mở mới, đóng các công ty, phân quyền admin cho các công ty.
  + admin công ty quản lý danh sách user, phân quyền và cấu hình thiết bị (máy tính, mobile, thiết bị ngoại vi: máy in), cấu hình kho, đội xe, các điều kiện cho phép nhân viên giao hàng (lái xe) thay đổi trạng thái hoàn thành giao hàng trên từng đơn: theo thời gian, tọa độ (kèm theo bán kính dung sai).
  + Quản lý thực hiện việc lập, phê duyệt, điều chỉnh kế hoạch/lệnh giao hàng, phân công lái xe, phụ xe, cập nhật thủ công trạng thái đơn hàng trong từng chuyến, xác nhận kết thúc chuyến.
  + Thủ kho: xác nhận xuất hàng/soạn hàng cho các lệnh giao hàng.
  + Nhân viên giao hàng: nhận kế hoạch, thực hiện giao hàng, cập nhật tình trạng giao của từng đơn.

## Nguyên tắc vận hành
- Thủ kho chỉ xác nhận được trạng thái xuất hàng cho các lệnh đã được duyệt.
- Nhân viên giao hàng chỉ cập nhật trạng thái giao hàng cho các đơn đã nằm trong lệnh được duyệt thuộc chuyến giao hàng được gán cho bản thân.
- Nhân viên giao hàng chỉ cập nhật được trạng thái giao hàng theo các điều kiện cho phép.


## Mô hình tổ chức hệ thống
- Hệ thống phục vụ nhiều công ty
- Mỗi công ty có bộ dữ liệu và quản lý độc lập
- Ứng dụng sử dụng 1 database cho tất cả các công ty

## Cách thức truy cập
- Web app: dùng cho quản lý, thủ kho
- mobile app: dùng cho nhân viên giao hàng

## Kiến trúc
Xem @docs/ARCHITECTURE.md trước khi thêm module mới.

## Kế hoạch 
Cập nhật roadmap và tiến độ trong @docs/PLAN.md
Dùng checkbox - [ ] / - [x], nhóm theo milestone

## Giả định
- Dữ liệu kế thừa từ các hệ thống khác đầy đủ các trường được yêu cầu.
- Đơn hàng được tách theo nhóm nhiệt độ (khô / lạnh+đông); không tách đơn theo khối lượng.
- Chưa xét thể tích hàng/xe (có thể bổ sung ở phase sau).
- Đại lý nhận hàng trong suốt khung giờ làm việc.
- Khi không đủ năng lực xe: vẫn sinh kế hoạch, kèm danh sách đơn không xếp được và cảnh báo.
- Bộ tối ưu tự chọn kho xuất hàng dựa trên tồn kho.
- Các giả định chưa xác nhận: xem bảng D9–D13 trong `docs/ARCHITECTURE.md`.
