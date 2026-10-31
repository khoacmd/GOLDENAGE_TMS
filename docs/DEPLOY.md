# Triển khai & vận hành production

> Bộ file: `infra/prod/` (Docker Compose, Caddy, nginx, backup/restore). Image: workflow **Images** (`.github/workflows/images.yml`) build `linux/amd64` + `linux/arm64`, đẩy lên `ghcr.io/khoacmd/tms-api`, `ghcr.io/khoacmd/tms-web`.

## 1. Kiến trúc chạy

```
Internet ──443/80──► caddy (HTTPS tự động, header bảo mật)
                       └─► web (nginx): SPA tĩnh · /api → api:8000 · /tiles (bản đồ) · /<bucket>/ → storage (ảnh, URL ký sẵn)
api (uvicorn, 2 worker) ─┬─ postgres (PostGIS, RLS)      migrate: chạy alembic rồi thoát
worker (Dramatiq) ───────┼─ redis (queue, cache, chống dò mật khẩu)
scheduler (mỗi phút) ────┘  storage (SeaweedFS S3)   osrm-car / osrm-motorbike (profile "routing")
```

Chỉ `caddy` mở cổng ra ngoài; các service khác nằm trong mạng nội bộ của compose.

## 2. Yêu cầu máy chủ

| | Không OSRM | Có OSRM (2 profile) |
|---|---|---|
| CPU / RAM | 2 vCPU / 4 GB | 4 vCPU / 8 GB (dựng dữ liệu OSRM cần ~4 GB RAM/profile) |
| Đĩa | 20 GB + ảnh | + ~9 GB OSRM, ~0,7 GB bản đồ |

Linux amd64 hoặc arm64, Docker Engine ≥ 24 + Compose v2, tên miền trỏ về IP máy chủ (bản ghi A), mở cổng 80/443.

## 3. Cài đặt lần đầu

```bash
# Trên máy chủ
git clone https://github.com/khoacmd/GOLDENAGE_TMS /opt/tms && cd /opt/tms/infra/prod
cp .env.example .env && chmod 600 .env
# Điền .env: SITE_ADDRESS/PUBLIC_URL (tên miền), DATA_DIR, mật khẩu & bí mật (openssl rand -hex 32)
docker compose pull            # hoặc: docker compose build (build tại chỗ)
docker compose up -d
docker compose ps              # api "healthy", migrate "Exited (0)"
curl -fsS https://<tên-miền>/health

# Tài khoản admin hệ thống (nhập mật khẩu ẩn)
docker compose exec api python -m app.cli create-system-admin --username sysadmin
```

Bản đồ tự host và định tuyến (tùy chọn, chạy trên máy chủ, ghi vào `DATA_DIR`):

```bash
DATA_ROOT=/srv/tms ../tiles/fetch-vietnam.sh        # → /srv/tms/tiles  (web tự dùng, không cần restart)
DATA_ROOT=/srv/tms ../osrm/prepare-vietnam.sh       # → /srv/tms/osrm   (~30 phút)
# .env: COMPOSE_PROFILES=routing, TMS_OSRM_CAR_URL=http://osrm-car:5000, TMS_OSRM_MOTORBIKE_URL=http://osrm-motorbike:5000
docker compose up -d
```

App mobile: chạy workflow **Mobile APK** với `api_url = https://<tên-miền>`.

## 4. Cập nhật phiên bản

```bash
git tag v1.2.0 && git push origin v1.2.0      # trên máy dev → workflow Images build & đẩy image
# Trên máy chủ: đặt TMS_VERSION=1.2.0 trong .env (hoặc latest)
cd /opt/tms && git pull && cd infra/prod
./backup.sh && docker compose pull && docker compose up -d   # migrate tự chạy trước api
```

Quay lui: đặt lại `TMS_VERSION` cũ. Nếu bản mới đã chạy migration không tương thích ngược → khôi phục backup trước khi cập nhật (mục 5).

## 5. Backup & khôi phục

- `./backup.sh`: `pg_dump` (định dạng custom) + nén ảnh SeaweedFS vào `$DATA_DIR/backup`, giữ `BACKUP_KEEP_DAYS` ngày.
  Cron: `0 2 * * * cd /opt/tms/infra/prod && ./backup.sh >> /var/log/tms-backup.log 2>&1`.
  **Bắt buộc** đồng bộ thêm `$DATA_DIR/backup` ra ngoài máy chủ (rclone/rsync tới object storage hoặc máy khác).
- `./restore.sh tms-<thời điểm>.dump [photos-<thời điểm>.tar.gz]`: dừng api/worker/scheduler/web, tạo lại database `tms` rồi nạp backup với quyền `tms_owner` (giữ nguyên RLS và quyền của `tms_app`), tùy chọn khôi phục ảnh (thư mục ảnh cũ được giữ lại tên `seaweedfs.before-restore-*`). Script dừng ở lỗi đầu tiên; sửa nguyên nhân rồi chạy lại.
- Đã diễn tập trên stack production (arm64): backup → sửa dữ liệu → khôi phục → dữ liệu và đăng nhập trở lại đúng, 24 bảng giữ RLS FORCE.
- Nên diễn tập khôi phục định kỳ (mỗi quý) trên máy khác.

## 6. Giám sát

- **Sống/chết**: `GET /health` (kiểm tra cả database). Healthcheck của compose dùng endpoint này; nên gắn thêm dịch vụ kiểm tra bên ngoài (UptimeRobot, Better Stack…) vào `https://<tên-miền>/health`.
- **Log**: mọi service ghi JSON 1 dòng/bản ghi ra stdout (`TMS_LOG_JSON=true` trong image), compose xoay vòng 20 MB × 5 file. Xem: `docker compose logs -f api worker scheduler`. Đăng nhập sai được ghi `WARNING` (tài khoản + IP).
- **Lỗi**: đặt `TMS_SENTRY_DSN` (Sentry hoặc GlitchTip tự host) → lỗi api/worker/scheduler gửi kèm phiên bản image; không gửi dữ liệu cá nhân (`send_default_pii=False`).
- Cần theo dõi thêm: dung lượng đĩa `DATA_DIR`, lần chạy lập kế hoạch `FAILED` (màn hình Kế hoạch), backup hằng ngày có file mới.

## 7. Mở công ty mới (onboarding)

Mỗi công ty là một tenant trong cùng database; dữ liệu cô lập bằng RLS (kiểm thử tự động: `backend/tests/test_security.py`). Đã kiểm chứng trên stack production: 2 công ty cùng import bộ dữ liệu mẫu (trùng mã kho/xe/đơn), lập kế hoạch song song qua worker + OSRM, không đọc được dữ liệu của nhau.

1. **Admin hệ thống** (web → Công ty): tạo công ty (mã, tên) kèm tài khoản admin công ty.
2. **Admin công ty** → Cấu hình: ngày làm việc, giờ ca, giờ cut-over, quy tắc xác nhận giao (thời gian, bán kính, ảnh bắt buộc), duyệt thiết bị, tham số lập kế hoạch (thời gian giao/điểm, quay đầu, số lượt/xe, chi phí cố định, hệ số thời gian di chuyển).
3. **Dữ liệu gốc** (Import dữ liệu, theo thứ tự `docs/samples/`): kho → đội xe → mặt hàng → khách hàng/điểm giao → tồn kho → đơn hàng. Hoặc cấp **API key** để hệ thống bán hàng đẩy dữ liệu (`docs/IMPORT_TEMPLATES.md`).
4. **Người dùng**: quản lý, thủ kho, lái xe/phụ xe (tài khoản thuộc công ty này).
5. **Thiết bị**: cài APK cho lái xe; nếu bật duyệt thiết bị thì admin duyệt máy ở trang Thiết bị. Khai báo máy in/PC nếu cần.
6. **Chạy thử 1 ngày**: lập kế hoạch tự động → duyệt → thủ kho xuất hàng → lái xe giao → kết thúc chuyến → xem báo cáo. Sau đó bật "Tự động lập kế hoạch theo lịch".

Đóng công ty: admin hệ thống tắt trạng thái hoạt động → mọi token của công ty đó bị từ chối ở request kế tiếp; dữ liệu vẫn giữ.

## 8. Thử stack production trên máy dev

```bash
cd infra/prod && cp .env.example .env
# SITE_ADDRESS=:80, PUBLIC_URL=http://localhost:58880, HTTP_PORT=58880, HTTPS_PORT=58443,
# DATA_DIR=<thư mục tạm>, IMAGE_PREFIX=local, TMS_VERSION=dev, điền mật khẩu
docker build -t local/tms-api:dev ../../backend && docker build -t local/tms-web:dev -f ../../web/Dockerfile ../..
docker compose up -d
```
