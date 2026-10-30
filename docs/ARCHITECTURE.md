# Kiến trúc hệ thống TMS (Transportation Management & Optimization)

> Tài liệu sống. Cập nhật khi có quyết định kiến trúc mới (xem mục 12 – Nhật ký quyết định).

## 1. Bối cảnh & quy mô

- Ngành: FMCG (sữa, đồ uống), giao cho đại lý cấp 1. Ba loại hàng: khô / lạnh / đông.
- Đa công ty (multi-tenant), 1 database dùng chung. Hiện tại: **1 công ty**, thiết kế sẵn để mở rộng.
- Quy mô công ty đầu tiên: **2 kho**, đội xe 4 chiếc:

| Xe | Loại | Trọng tải |
|---|---|---|
| Xe tải | Ô tô | 2.000 kg |
| Xe Van | Ô tô | 945 kg |
| Xe máy #1 | Xe máy | 250 kg |
| Xe máy #2 | Xe máy | 250 kg |

  → Tổng năng lực ~3.445 kg/lượt. Bài toán tối ưu nhỏ (vài chục – vài trăm điểm/ngày), giải trong vài giây đến vài chục giây.
- Kênh truy cập: **Web** (admin, quản lý, thủ kho) và **Mobile** (nhân viên giao hàng).

## 2. Kiến trúc tổng thể

**Modular monolith** cho API + **worker** tách riêng cho tác vụ nặng (tối ưu tuyến, import, job định kỳ).

```
 Web (React)                       Mobile (React Native / Expo)
 Admin · Quản lý · Thủ kho         Lái xe / Phụ xe
        │                                   │
        └──────────── HTTPS / REST (OpenAPI) ┘
                          │
        ┌──────────────────────────────────────────┐
        │ Backend API – FastAPI (modular monolith) │
        │ tenancy · identity · master_data ·       │
        │ integration · orders · inventory ·       │
        │ planning · dispatch · warehouse ·        │
        │ delivery · costing · reporting           │
        └───────┬──────────────┬───────────────────┘
                │              │ enqueue job
                │              ▼
                │        Redis ──► Worker (Dramatiq) + Scheduler
                │                   ├─ optimization (OR-Tools)
                │                   ├─ import / sync tích hợp
                │                   └─ job lập kế hoạch định kỳ
                ▼                          │
   PostgreSQL 16 + PostGIS (RLS)           ▼
   Object storage S3 (ảnh)           OSRM (bản đồ OSM Việt Nam,
                                     profile car + motorbike)
   Hệ thống bán hàng / tồn kho ngoài ──► API tích hợp / upload file
```

## 3. Tech stack

| Lớp | Công nghệ |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Quản lý package / chất lượng | `uv`, `ruff`, `mypy`, `pytest` |
| Database | PostgreSQL 16 + PostGIS (image multi-arch `imresamu/postgis`, vì `postgis/postgis` chỉ có amd64) |
| Job/queue | Redis + Dramatiq, APScheduler (job định kỳ theo cấu hình công ty) |
| Tối ưu | Google OR-Tools (Routing Solver) |
| Routing / khoảng cách | OSRM tự host (OSM Việt Nam) – ma trận khoảng cách/thời gian theo profile ô tô & xe máy |
| Lưu file | S3-compatible qua boto3: SeaweedFS khi tự host (image MinIO trên Docker Hub không còn truy cập được), S3 của nhà cung cấp cloud ở production; test dùng bộ nhớ (`TMS_STORAGE_BACKEND=memory`) |
| Web | React 19 + TypeScript + Vite, Ant Design, React Router, TanStack Query, MapLibre GL (từ M1) |
| Mobile | React Native (Expo SDK 58), TypeScript, expo-secure-store (token); từ M3: SQLite offline queue, expo-location, expo-camera |
| Dùng chung TS | pnpm workspace; client/type sinh tự động từ OpenAPI (`openapi-typescript`) |
| Auth | JWT access + refresh token, RBAC theo công ty |
| Triển khai | Docker Compose trên 1 VPS (cloud-agnostic), nâng cấp K8s khi cần |
| Giám sát | Sentry (lỗi), log JSON có cấu trúc, Prometheus/Grafana (giai đoạn sau) |

Múi giờ nghiệp vụ: `Asia/Ho_Chi_Minh`; lưu DB dạng `timestamptz` (UTC).

## 4. Cấu trúc repository

```
backend/
  app/
    core/            # config, db session, security, tenancy context, errors
    modules/
      <module>/      # models.py, schemas.py, repository.py, service.py, router.py
    main.py
  worker/            # dramatiq actors, scheduler
  optimization/      # bộ giải VRP – thuần Python, không phụ thuộc FastAPI/DB
  migrations/        # alembic
  tests/
web/                 # React app
mobile/              # Expo app
packages/api-client/ # TS client sinh từ OpenAPI
infra/               # docker-compose, osrm, nginx
docs/
```

Quy tắc module:
- Module chỉ gọi module khác qua `service` công khai, không truy cập trực tiếp bảng của module khác.
- `optimization/` nhận input là dataclass thuần, trả output thuần → test độc lập, có thể tách service sau này.

## 5. Đa công ty (multi-tenancy)

- Mọi bảng nghiệp vụ có cột `company_id NOT NULL`.
- Bật **PostgreSQL Row-Level Security** (ENABLE + FORCE): mỗi request/job đặt `set_config('app.company_id', ..., true)` theo transaction; policy `company_id = app_current_company()`. Context được lưu trên session và tự áp lại mỗi khi transaction mới bắt đầu.
- Role DB: `tms_owner` (sở hữu schema, chạy migration) và `tms_app` (runtime, không phải owner/superuser → luôn chịu RLS). Không dùng `BYPASSRLS`.
- Bảng dùng chung không áp RLS: `companies` (danh mục công ty) và `users` (tài khoản toàn hệ thống; quyền theo công ty nằm ở `user_roles`). System admin thao tác dữ liệu một công ty bằng cách chuyển context sang công ty đó.
- `user_roles` có thêm policy `own_roles`: user luôn đọc được vai trò của chính mình ở mọi công ty (cần khi đăng nhập/chọn công ty).
- `users.home_company_id`: công ty sở hữu tài khoản. Chỉ admin công ty này được đổi mật khẩu/khóa tài khoản (admin công ty khác không thấy được vai trò của user ở công ty khác do RLS).
- `api_keys` có policy `api_key_lookup`: trước khi biết công ty, chỉ đọc được đúng key có prefix đang xác thực (`app.api_key_prefix`).
- Khóa duy nhất nghiệp vụ luôn kèm `company_id` (vd. `UNIQUE(company_id, code)`).
- Cấu hình theo công ty (`company_settings`): ngày làm việc trong tuần, giờ ca (mặc định T2–T7, 07:00–19:00), giờ cut-over, lịch chạy job lập kế hoạch, thời gian phục vụ mặc định mỗi điểm, thời gian quay đầu tại kho, quy tắc xác nhận giao.

## 6. Phân quyền (RBAC)

| Vai trò | Phạm vi |
|---|---|
| `system_admin` | Mở/đóng công ty, gán company admin |
| `company_admin` | User & vai trò, thiết bị (PC, mobile, máy in), kho, đội xe, quy tắc xác nhận giao |
| `manager` | Lập/duyệt/điều chỉnh kế hoạch & lệnh, phân công lái xe/phụ xe, cập nhật thủ công trạng thái đơn, xác nhận kết thúc chuyến |
| `warehouse_keeper` | Xác nhận soạn/xuất hàng cho lệnh **đã duyệt**; có thể giới hạn theo kho |
| `driver` | Xem chuyến được gán cho mình; cập nhật trạng thái đơn thuộc lệnh **đã duyệt** của chuyến mình, theo điều kiện cho phép |

Một user có thể có nhiều vai trò trong một công ty. Phân quyền kiểm tra ở tầng service (không chỉ ở router).

## 7. Mô hình dữ liệu (lõi)

### Dữ liệu gốc
- `companies`, `company_settings`
- `users`, `user_roles(company_id, user_id, role, warehouse_id?)`, `devices(device_type: PC|MOBILE|PRINTER, name, identifier, status: ACTIVE|PENDING|BLOCKED, warehouse_id?, user_id?, model/os/app_version, connection/address/paper_size (máy in), last_seen_at)`
- `warehouses(code, name, address, location geography(Point))`
- `vehicles(code, name, plate_no, vehicle_type: CAR|MOTORBIKE, capacity_kg, cost_per_km, requires_assistant, cargo_class: DRY_ONLY|COLD_ONLY|ANY, cost_allocation_method: ORDER_VALUE|DISTANCE|WEIGHT|PER_TRIP, active)`
- `vehicle_warehouses(vehicle_id, warehouse_id)` – kho xe được phép lấy hàng
- `customers(code, name, address, contact, required_vehicle_type: CAR|MOTORBIKE|ANY, sales_rep, delivery_weekdays[], deliveries_per_week)`
- `delivery_points(customer_id, address, location geography(Point))`
- `products(code, name, temp_class: DRY|CHILLED|FROZEN, uom, weight_kg)` – đồng bộ từ hệ thống bán hàng
- `inventory_balances(warehouse_id, product_id, qty_on_hand, synced_at)`. Giữ chỗ tồn **không có bảng riêng**: tồn khả dụng = tồn snapshot − hàng của các lệnh `DRAFT/APPROVED` (chưa xuất kho) tại kho đó (`dispatch.stock_available`) - lệnh nháp do bộ tối ưu sinh ra chính là phần giữ chỗ (D23).

### Đơn hàng
- `sales_orders(external_ref, customer_id, delivery_point_id, requested_date, order_value, status)`
- `sales_order_lines(product_id, qty, weight_kg)`
- **`order_parts`** – *đơn vị lập kế hoạch*: mỗi đơn tách tối đa 2 phần theo nhóm nhiệt độ
  - `temp_group: DRY | COLD` (COLD = lạnh + đông), `weight_kg`, `value`, `warehouse_id?`, `status: PENDING|PLANNED|DELIVERED|FAILED|CANCELLED`, `attempt_count`
  - **Không tách theo khối lượng**: một `order_part` luôn đi nguyên trên một chuyến.

### Kế hoạch & chuyến
- **Kế hoạch ngày** = tập các lệnh có cùng `plan_date` (không có bảng riêng); mỗi lần lập tự động lưu `planning_runs(plan_date, trigger: MANUAL|SCHEDULED, status: QUEUED|RUNNING|SUCCEEDED|FAILED, replace_drafts, distance_source, input_snapshot, summary, unassigned[], warnings[], error)`.
- `trips` – **Lệnh giao = Chuyến (1–1)**, mã `L{yyMMdd}-{nn}`, hai trục trạng thái:
  - `plan_date, vehicle_id, warehouse_id, driver_id?, assistant_id?, trip_seq` (lượt thứ mấy của xe trong ngày)`, source: MANUAL|AUTO, total_weight_kg, total_value`, mốc thời gian duyệt/xuất kho/xuất phát/kết thúc.
  - `order_status` (lệnh): `DRAFT → APPROVED → PICKED → DISPATCHED → CLOSED` (+ `CANCELLED`)
  - `delivery_status` (chuyến): `NOT_STARTED | IN_PROGRESS | FINISHED`; thống kê thành công/thất bại/hủy tính từ item.
  - Lệnh tự động: `planning_run_id, planned_distance_km, planned_cost, planned_start/end` (ước tính lúc lập).
- `trip_stops(trip_id, seq, delivery_point_id? | name + address + latitude/longitude)` – lệnh thủ công có thể có điểm dừng tự do.
- `trip_items(trip_id, stop_id, order_part_id? | description, weight_kg, value, status, reason, delivered_at, updated_by, is_manual_update)`; unique index: 1 phần đơn chỉ nằm trong 1 item chưa hủy.

### Giao hàng
- `delivery_rules(company_id)`: cửa sổ thời gian được phép xác nhận, bán kính dung sai (m), bắt buộc ảnh, cho phép xác nhận offline.
- `delivery_confirmations(trip_item_id, result: SUCCESS|FAILED, reason_code, delivered_at, recorded_at, device_time, lat, lng, distance_to_point_m, rule_check jsonb, confirmed_by, is_manual_override)`
- `delivery_photos(confirmation_id, object_key)`
- `audit_logs(entity, entity_id, action, data jsonb, user_id, created_at)` – mọi thay đổi trạng thái lệnh & cập nhật giao hàng (đã có từ M2).

## 8. Luồng trạng thái & nguyên tắc vận hành

```
order_part: PENDING ──(vào lệnh)──► PLANNED ──► DELIVERED
              ▲  ▲                       └───► FAILED (attempt_count+1) ── xếp lệnh lại được
              │  └──── hủy lệnh / hủy item (về PENDING, hoặc FAILED nếu đã từng thất bại)
              └──────── sửa lệnh bỏ phần đơn ra
trip.order_status:  DRAFT ─duyệt─► APPROVED ─thủ kho─► PICKED ─lái xe nhận─► DISPATCHED ─QL xác nhận kết thúc─► CLOSED
```

- Phần đơn được xếp lệnh khi `PENDING` hoặc `FAILED` (giao lại), đơn `OPEN`, ngày giao yêu cầu ≤ ngày lập lệnh. Vào lệnh (kể cả nháp) → `PLANNED` để không xếp trùng.
- Ràng buộc **chặn** khi lưu lệnh: xe hoạt động, kho thuộc danh sách kho của xe, lái xe/phụ xe có vai trò `driver`, phụ xe bắt buộc nếu xe yêu cầu, phần đơn đúng điểm dừng, loại hàng hợp `cargo_class` của xe, loại xe đúng yêu cầu của khách, tổng khối lượng ≤ trọng tải. **Cảnh báo** (vẫn lưu): tồn kho tại kho xuất không đủ (trừ phần đã giữ bởi lệnh khác chưa xuất kho), ngày giao khác ngày yêu cầu, ngày không phải ngày giao hàng.
- Duyệt cần có lái xe. Sửa lệnh sau `APPROVED` → quay về `DRAFT`, cần duyệt lại; sau `PICKED` không sửa/hủy được (chưa có luồng hoàn trả kho).
- Quyền: lập/sửa/duyệt/hủy/cập nhật giao/kết thúc = `manager`; xác nhận xuất kho = `warehouse_keeper`; xuất phát = `manager` hoặc lái xe/phụ xe của chuyến.
- Thủ kho chỉ xác nhận `PICKED` cho lệnh `APPROVED`.
- Lái xe chỉ xác nhận item thuộc trip `DISPATCHED` mà mình là `driver_id` (hoặc `assistant_id`).
- Item trong chuyến có trạng thái `PENDING → SUCCESS | FAILED | CANCELLED`.
- `trip.delivery_status` chuyển sang `FINISHED` ("Kết thúc") khi **không còn item `PENDING`**, kể cả khi có đơn thất bại. Chuyến lưu kèm thống kê thành công / thất bại / hủy.
- **Chỉ quản lý** được hủy (`CANCELLED`) item đang `PENDING`, phải ghi lý do và có audit. Lái xe không được hủy.
- Phần đơn `FAILED` giữ trạng thái (kèm `attempt_count`) và **được xếp lại** ở lần lập kế hoạch kế tiếp; phần đơn bị hủy khỏi chuyến quay về `PENDING`. Muốn hủy hẳn đơn hàng thì quản lý hủy đơn (chỉ khi chưa vào lệnh).
- Đơn chuyển `COMPLETED` khi mọi phần đơn (không tính đã hủy) `DELIVERED`.

## 9. Lập kế hoạch tự động (module `planning` + `optimization`)

Đầu vào tại thời điểm cut-over: mọi `order_part` `PENDING` (kể cả thất bại trước đó) có `requested_date ≤ plan_date`.

1. **Kiểm tra khả thi từng phần đơn** → loại các phần không thể xếp, ghi lý do:
   - Xe tương thích: `cargo_class` khớp `temp_group`; `vehicle_type` khớp yêu cầu khách; `weight_kg ≤ capacity_kg`.
   - Ví dụ: phần đơn > 250 kg chỉ đi ô tô; > 2.000 kg → không xếp được (báo quản lý).
2. **Chọn kho theo tồn**: với mỗi phần đơn, kho ứng viên = kho đủ tồn (trừ phần đã giữ chỗ) **và** có xe tương thích được gán kho đó. Heuristic tham lam (đơn yêu cầu sớm / từng giao thất bại xếp trước): ưu tiên kho đáp ứng được mọi phần của cùng điểm giao (giảm số lần giao), sau đó kho gần nhất. Chưa có dữ liệu tồn kho → chọn kho gần nhất, có cảnh báo.
   - *Giai đoạn sau*: đưa lựa chọn kho vào trong bộ giải (alternative nodes) nếu heuristic chưa đủ tốt.
3. **Ma trận khoảng cách/thời gian** từ OSRM theo profile ô tô và xe máy (cache theo cặp điểm).
4. **Giải VRP bằng OR-Tools**:
   - Nhiều kho; mỗi chuyến xuất phát & kết thúc tại 1 kho.
   - **Nhiều lượt/xe**: mỗi xe vật lý được nhân thành N "xe ảo" (lượt 1..N) ràng buộc `start(lượt k+1) ≥ end(lượt k) + thời gian quay đầu`.
   - Ràng buộc: tải trọng kg; ca làm việc (khung giờ nhận hàng của đại lý = giờ làm việc); thời gian phục vụ mỗi điểm; `SetAllowedVehiclesForIndex` cho tương thích xe.
   - Các phần đơn cùng điểm giao, cùng nhóm nhiệt độ → gộp 1 node. Phần DRY & COLD cùng điểm → 2 node khoảng cách 0, ưu tiên cùng xe khi xe `ANY`.
   - Hàm mục tiêu: Σ(km × `cost_per_km` của xe) + chi phí cố định mỗi lượt (giảm số chuyến).
   - Bỏ node có penalty rất lớn → nếu không đủ năng lực, bộ giải vẫn trả kết quả, danh sách **không xếp được** kèm lý do để quản lý xử lý thủ công (thêm lượt, xe thuê ngoài).
5. **Kết quả**: kế hoạch `DRAFT` → quản lý xem trên bản đồ, kéo thả điều chỉnh → duyệt.

Kích hoạt: lệnh manual (`POST /planning/runs`) hoặc job định kỳ (`worker/scheduler.py`, mỗi phút): công ty bật `auto_plan_enabled`, đã qua `cutover_time` → lập cho **ngày làm việc kế tiếp**, mỗi ngày 1 lần. Chạy nền bằng Dramatiq (`worker/tasks.py`, queue `planning`, `--threads 1` vì mỗi message dùng event loop riêng); `TMS_TASKS_EAGER=true` chạy ngay trong API (test/dev không có worker). Mỗi lần chạy lưu `planning_runs` (snapshot input) để tái hiện/debug.

Chi tiết triển khai:
- Tham số theo công ty: thời gian giao mỗi điểm, quay đầu tại kho, số lượt tối đa/xe, chi phí cố định/chuyến, thời gian tối ưu tối đa. Lượt đã có trong ngày (lệnh thủ công) được trừ khỏi số lượt của xe. Lập trong ngày → chuyến xuất phát từ hiện tại + 15 phút.
- `replace_drafts`: hủy lệnh `AUTO` còn `DRAFT` của ngày rồi lập lại; lệnh đã duyệt/thủ công giữ nguyên.
- Lệnh tự động chưa có lái xe/phụ xe; khi duyệt bắt buộc có lái xe và phụ xe nếu xe yêu cầu.
- Ma trận khoảng cách (`app/modules/routing`): OSRM `/table` (cache Redis theo cặp điểm, 30 ngày) → lỗi/chưa cấu hình thì ước lượng đường chim bay × 1,35, ô tô 22 km/h, xe máy 25 km/h. Profile xe máy (`infra/osrm/motorbike.lua`): không đi cao tốc, tối đa 50 km/h.
- Bộ giải (`optimization/vrp.py`): mỗi xe nhân thành `max_trips × số kho` xe ảo, chuỗi thời gian `start(k+1) ≥ end(k) + quay đầu × active(k)`; phần đơn cùng điểm + nhóm nhiệt độ + kho gộp 1 node (vượt tải xe lớn nhất thì chia nhiều node, không tách phần đơn); OR-Tools `PATH_CHEAPEST_ARC` + `GUIDED_LOCAL_SEARCH`. (OR-Tools 9.15: `SetAllowedVehiclesForIndex` lỗi binding Python → dùng `VehicleVar(i).SetValues([-1, ...])`.)
- Điều chỉnh: kéo thả điểm dừng giữa các chuyến / đổi thứ tự (`POST /planning/move-stop`, 1 transaction, kiểm tra ràng buộc như lập tay); trang kết quả so chi phí hiện tại với phương án tối ưu.

## 10. Tích hợp

- Đối tượng: đơn hàng, mặt hàng, khách hàng/điểm giao, tồn kho.
- Hai kênh dùng chung một pipeline (`app/core/importing.py` + `app/modules/integration`):
  - **Upload file** `.xlsx`/`.csv`: `POST /api/v1/imports/{loại}` (người dùng web).
  - **API tích hợp**: `POST /api/v1/integration/{loại}` với header `X-API-Key` (key theo công ty, chỉ lưu SHA-256, thu hồi được); body `{"rows": [...], "dry_run": false}`.
- Mỗi loại dữ liệu khai báo một `ImportSpec` (cột template, model Pydantic cho 1 dòng, hàm `apply`) ở module sở hữu dữ liệu (`master_data/importers.py`, `orders/importers.py`, `inventory/importers.py`), đăng ký trong `integration/registry.py`.
- Header nhận nhãn tiếng Việt hoặc mã cột; lỗi trả theo dòng/cột bằng tiếng Việt; **all-or-nothing** (savepoint); `dry_run` kiểm tra không ghi; mọi lần chạy lưu `import_jobs`.
- Upsert **idempotent** theo mã (`code` / `external_ref`, không phân biệt hoa thường); tồn kho là snapshot thay toàn bộ theo kho kèm `synced_at`.
- Đơn đã vào kế hoạch/giao/hủy bị **khóa**: lần đồng bộ sau báo lỗi cho dòng đó, không ghi đè.
- Template chuẩn và tài liệu: `docs/IMPORT_TEMPLATES.md` (sinh từ code), dữ liệu mẫu `docs/samples/`.

## 11. Mobile & xác nhận giao hàng

- App (Expo SDK 58) lưu hàng đợi xác nhận trong SQLite (`expo-sqlite/kv-store`), ảnh chép vào thư mục document của app; gửi khi có mạng (NetInfo), khi mở lại app và mỗi 30 giây. Mỗi thao tác có `client_id` (UUID) → server idempotent (`UNIQUE(company_id, client_id)`).
- Request trong hàng đợi: tự nạp token từ SecureStore, gặp 401 thì làm mới token rồi thử lại; timeout 30 giây bằng `Promise.race` (fetch của Expo không luôn tôn trọng abort); lượt gửi treo quá 2 phút bị bỏ qua.
- Mỗi xác nhận gửi kèm: GPS, độ chính xác, cờ vị trí giả lập (`mocked`), giờ thiết bị, khóa ảnh đã upload.
- **Server là nơi quyết định** (`app/modules/delivery`): đúng người (lái xe/phụ xe của chuyến), chuyến `DISPATCHED`, mục còn `PENDING`, giờ thiết bị trong [ca − dung sai, ca + dung sai] của ngày giao, khoảng cách tới điểm giao ≤ bán kính (haversine), không dùng vị trí giả lập, có ảnh nếu bắt buộc, gửi không quá `offline_max_delay_minutes` sau thao tác (thiết bị nhanh hơn server tối đa 5 phút).
- **Mọi lần xác nhận đều lưu** `delivery_confirmations` (+ `delivery_photos`), kể cả bị từ chối (`accepted=false`, `violations`, `rule_check`); chỉ lần hợp lệ mới cập nhật trạng thái mục hàng. App hiển thị lý do bị từ chối để lái xe xác nhận lại.
- `delivered_at` = giờ thao tác trên thiết bị; quản lý có thể sửa thủ công trên web (ghi audit).
- Ảnh: app upload qua API (`POST /driver/photos`, JPEG/PNG/WebP ≤ 8MB, key theo `company_id/`), server lưu S3 (SeaweedFS khi tự host); web xem bằng URL ký sẵn (`TMS_S3_PUBLIC_ENDPOINT`).
- Định vị: `expo-location` (Fused Location của Google Play Services) trước; lỗi thì dùng module native `mobile/modules/tms-location` (LocationManager GPS/mạng, không cần Play Services, bỏ vị trí cũ hơn 5 phút). Module này chỉ có trong bản APK, không có trong Expo Go.
- Thiết bị: app sinh mã cài đặt (SecureStore), tự đăng ký `POST /driver/device` khi mở app và gửi kèm `device_id` trong mỗi xác nhận. Thiết bị `BLOCKED` (hoặc `PENDING`/chưa đăng ký khi công ty bật `require_device_approval`) → xác nhận bị từ chối (vẫn lưu). PC/máy in do admin công ty khai báo; in vẫn qua trình duyệt (D17).
- Build APK: GitHub Actions x86-64 (`mobile-apk.yml`), `expo prebuild` + Gradle; URL API gắn vào bản build; HTTP thường chỉ bật khi URL là `http://` (`app.config.ts`). Bản pilot ký bằng debug keystore của template.

## 12. Triển khai

Docker Compose: `api`, `worker`, `scheduler`, `postgres`, `redis`, `storage` (SeaweedFS S3), `osrm-car`, `osrm-motorbike`, `web` (nginx).

| Môi trường | Hạ tầng | Ghi chú |
|---|---|---|
| dev/test | Máy DGX Spark hiện tại (**ARM64/aarch64**, 20 core, 121 GB RAM) | Mọi image phải hỗ trợ `linux/arm64`; mobile chạy giả lập |
| production | Cloud VPS (khuyến nghị 4 vCPU / 8 GB, thường là amd64) | OSRM Việt Nam cần ~2–3 GB RAM/profile; build image multi-arch (`docker buildx`) |

Image đã kiểm tra có `arm64`: `imresamu/postgis:16-3.4`, `ghcr.io/project-osrm/osrm-backend`, `redis:7`, `chrislusf/seaweedfs`.

**Mobile trên Spark (ARM64):** Android Emulator của Google chủ yếu phát hành cho host x86_64, nên cần kiểm chứng ở M0. Thứ tự phương án:
1. **Redroid** (Android chạy trong container, hỗ trợ arm64 gốc, máy có `/dev/kvm`) + `adb` + `scrcpy` để thao tác.
2. Expo Go trên điện thoại thật qua mạng LAN, dùng để kiểm thử GPS và camera thật.
3. Expo web, chỉ để xem nhanh giao diện (không thay thế được kiểm thử GPS/camera).

Kiểm thử điều kiện tọa độ trên giả lập: dùng `adb emu geo fix` hoặc mock location.

Ghi nhận khi dựng M0 trên Spark:
- **Đã kiểm chứng**: Redroid `14.0.0_64only` (arm64) + Expo Go SDK 58 chạy được app, đăng nhập qua backend thật. Cần `sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"`; adb chạy trong container (không có bản adb arm64 cài sẵn). Hướng dẫn: `infra/android/README.md`.
- Trình biên dịch Hermes (`hermesc`) đi kèm React Native chỉ có bản x86-64 → `expo export` cần `--no-bytecode` trên Spark; build APK release nên chạy trên CI x86-64 hoặc EAS Build. Chế độ dev qua Metro không bị ảnh hưởng.
- TypeScript: web dùng TS 7 (bản native); `packages/api-client` ghim TS 5.9 vì `openapi-typescript` cần API compiler JS; mobile dùng TS theo SDK Expo.

## 13. Giả định & quyết định

| # | Nội dung | Trạng thái |
|---|---|---|
| D1 | Modular monolith + worker, chưa tách microservices | Chốt |
| D2 | Đa công ty bằng `company_id` + PostgreSQL RLS | Chốt |
| D3 | Tách đơn theo nhóm nhiệt độ DRY / COLD (lạnh+đông); **không** tách theo khối lượng | Chốt |
| D4 | Chưa xét thể tích; thiết kế để thêm `volume` cho xe & mặt hàng ở phase sau | Chốt |
| D5 | Đại lý nhận hàng suốt giờ làm việc (không có time window riêng từng điểm) | Chốt |
| D6 | Không đủ năng lực → vẫn sinh kế hoạch + danh sách không xếp được + cảnh báo | Chốt |
| D7 | Bộ tối ưu tự chọn kho theo tồn kho | Chốt |
| D8 | Lệnh giao và chuyến 1–1, gộp chung bảng `trips` | Chốt |
| D9 | Tần suất giao của khách chỉ dùng để **cảnh báo** khi ngày yêu cầu không khớp, không phải ràng buộc cứng | Chốt |
| D10 | Chuyến "Kết thúc" khi không còn đơn pending (kể cả có đơn thất bại), kèm thống kê; chỉ quản lý được hủy đơn pending | Chốt |
| D11 | "Phương pháp ghi nhận chi phí" = cách phân bổ chi phí chuyến về từng đơn; không dùng làm hàm mục tiêu tối ưu | Chốt |
| D12 | Docker Compose; dev/test trên DGX Spark (ARM64), mobile giả lập; production trên cloud VPS | Chốt |
| D13 | Một chuyến chỉ lấy hàng tại 1 kho (giai đoạn này; có thể mở ở phase sau) | Chốt tạm |
| D14 | Item bị quản lý hủy khỏi chuyến quay về `PENDING` để lập lại kế hoạch (không hủy hẳn đơn) | Chốt |
| D15 | Không có bảng kế hoạch ngày riêng: kế hoạch = các lệnh cùng `plan_date` | Chốt (M2) |
| D16 | Bản đồ: MapLibre + tile OSM công cộng khi dev; production cấu hình `VITE_MAP_TILE_URL` (nhà cung cấp tile/tự host) | Chốt (M2) |
| D17 | In phiếu soạn hàng / giao hàng bằng trang in của trình duyệt (In / Lưu PDF), chưa sinh PDF phía server | Chốt (M2) |
| D18 | Chỉ quản lý lập/duyệt/cập nhật lệnh; admin công ty chỉ xem kế hoạch | Chốt |
| D19 | Hoàn trả kho sau xuất kho, giới hạn thủ kho theo kho: để phase sau | Chốt |
| D20 | Bản đồ tự host bằng PMTiles (Protomaps, vùng Việt Nam + Hoàng Sa, Trường Sa) phục vụ tĩnh qua nginx (`/tiles`); chưa có dữ liệu thì dùng tile OSM | Chốt (M3) |
| D21 | Xác nhận giao vi phạm quy tắc vẫn được lưu (để kiểm tra), không cập nhật trạng thái | Chốt (M3) |
| D22 | Thiết bị mobile tự đăng ký; duyệt trước khi dùng là tùy chọn theo công ty; khóa thiết bị chặn xác nhận giao | Chốt (M3) |
| D23 | Giữ chỗ tồn = lệnh chưa xuất kho (không có bảng `inventory_reservations` riêng) | Chốt (M4) |
| D24 | Kho xuất chọn trước bằng heuristic rồi mới giải VRP; đưa chọn kho vào bộ giải ở phase sau | Chốt (M4) |
| D25 | Phần đơn giao thất bại được xếp lại: unique "phần đơn đang hiệu lực" chỉ tính item `PENDING`/`SUCCESS` | Chốt (M4) |
