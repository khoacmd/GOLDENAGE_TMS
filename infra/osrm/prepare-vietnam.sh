#!/usr/bin/env bash
# Dựng dữ liệu định tuyến OSRM cho Việt Nam (OpenStreetMap, Geofabrik), 2 profile: car, motorbike.
# Dùng: infra/osrm/prepare-vietnam.sh   → infra/data/osrm/{car,motorbike}/vietnam.osrm*
# Sau đó: docker compose -f infra/docker-compose.yml --profile routing up -d osrm-car osrm-motorbike
# và cấu hình backend: TMS_OSRM_CAR_URL=http://localhost:55000 TMS_OSRM_MOTORBIKE_URL=http://localhost:55001
# Cần ~4 GB RAM và vài GB đĩa; chạy lại để cập nhật bản đồ mới.
set -euo pipefail
cd "$(dirname "$0")/.."
IMAGE=ghcr.io/project-osrm/osrm-backend:v6.0.0
OUT=data/osrm
PBF=$OUT/vietnam-latest.osm.pbf
mkdir -p "$OUT/car" "$OUT/motorbike"

if [[ ! -f $PBF || -n ${REFRESH:-} ]]; then
  echo "Tải dữ liệu OSM Việt Nam (Geofabrik) ..."
  curl -fL --retry 5 -C - -o "$PBF.tmp" https://download.geofabrik.de/asia/vietnam-latest.osm.pbf
  mv "$PBF.tmp" "$PBF"
fi

for profile in car motorbike; do
  echo "== Dựng profile $profile"
  dir=$OUT/$profile
  rm -f "$dir"/vietnam.osrm*
  ln -f "$PBF" "$dir/vietnam.osm.pbf"
  lua=/opt/car.lua
  [[ $profile == motorbike ]] && lua=/profiles/motorbike.lua
  run() { docker run --rm -v "$PWD/$dir:/data" -v "$PWD/osrm:/profiles:ro" "$IMAGE" "$@"; }
  run osrm-extract -p "$lua" /data/vietnam.osm.pbf
  run osrm-partition /data/vietnam.osrm
  run osrm-customize /data/vietnam.osrm
  rm -f "$dir/vietnam.osm.pbf"
done
echo "Xong: $OUT"
