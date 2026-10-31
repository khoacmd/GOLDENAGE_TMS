#!/usr/bin/env bash
# Khôi phục database từ 1 bản backup: ./restore.sh tms-YYYYmmdd-HHMMSS.dump [photos-....tar.gz]
# Dừng api/worker/scheduler trong lúc khôi phục; mọi dữ liệu hiện tại của database tms bị thay thế.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a

dump=${1:?Cần tên file .dump trong $DATA_DIR/backup}
photos=${2:-}
[ -f "$DATA_DIR/backup/$dump" ] || { echo "Không thấy $DATA_DIR/backup/$dump"; exit 1; }
read -r -p "Thay toàn bộ database tms bằng $dump? Gõ 'khoi phuc' để tiếp tục: " answer
[ "$answer" = "khoi phuc" ] || exit 1

docker compose stop api worker scheduler web
# Tạo lại database rỗng (extension do superuser sở hữu), rồi nạp dữ liệu với quyền tms_owner.
docker compose exec -T postgres psql -U postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS tms WITH (FORCE)" \
  -c "CREATE DATABASE tms OWNER tms_owner"
docker compose exec -T postgres psql -U postgres -d tms -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS postgis" \
  -c "CREATE EXTENSION IF NOT EXISTS pgcrypto" \
  -c "ALTER SCHEMA public OWNER TO tms_owner"
# Bỏ các mục thuộc extension (đã tạo ở trên; chỉ superuser được sửa): EXTENSION, bảng spatial_ref_sys của PostGIS.
docker compose exec -T postgres sh -c "pg_restore -l /backup/$dump | grep -v -e ' EXTENSION ' -e ' spatial_ref_sys ' > /tmp/restore.list && \
  pg_restore -U postgres -d tms --no-owner --role=tms_owner --single-transaction --exit-on-error \
  -L /tmp/restore.list /backup/$dump"

if [ -n "$photos" ]; then
  docker compose stop storage
  docker run --rm -v "$DATA_DIR":/data alpine:3.20 sh -c \
    "mv /data/seaweedfs /data/seaweedfs.before-restore-$(date -u +%s) && tar -C /data -xzf /data/backup/$photos"
  docker compose start storage
fi

docker compose up -d
echo "Đã khôi phục. Kiểm tra: curl -fsS \$PUBLIC_URL/health"
