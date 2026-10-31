#!/usr/bin/env bash
# Backup hằng ngày: database (pg_dump định dạng custom) + ảnh chứng từ (SeaweedFS) vào $DATA_DIR/backup.
# Cron gợi ý (2h sáng): 0 2 * * * cd /opt/tms/infra/prod && ./backup.sh >> /var/log/tms-backup.log 2>&1
# Nên đồng bộ thêm $DATA_DIR/backup ra ngoài máy chủ (rclone/rsync tới object storage khác).
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a

stamp=$(date -u +%Y%m%d-%H%M%S)
dir="$DATA_DIR/backup"
# File dữ liệu do container tạo (root) → thao tác qua container để không cần sudo.
in_data() { docker run --rm -v "$DATA_DIR":/data alpine:3.20 "$@"; }

echo "[$(date -u +%FT%TZ)] backup database → tms-$stamp.dump"
docker compose exec -T postgres pg_dump -U postgres -d tms -Fc -f "/backup/tms-$stamp.dump"

echo "[$(date -u +%FT%TZ)] backup ảnh → photos-$stamp.tar.gz"
# Ảnh chỉ được thêm mới (không sửa) nên chép khi đang chạy vẫn dùng được.
in_data tar -C /data -czf "/data/backup/photos-$stamp.tar.gz" seaweedfs

in_data find /data/backup -maxdepth 1 -type f \( -name 'tms-*.dump' -o -name 'photos-*.tar.gz' \) \
  -mtime +"${BACKUP_KEEP_DAYS:-14}" -print -delete
ls -lh "$dir" | tail -n 4
