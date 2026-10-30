#!/usr/bin/env bash
# Tải bản đồ vector Việt Nam (PMTiles, dữ liệu OpenStreetMap qua Protomaps) + font/icon để tự host.
# Dùng: infra/tiles/fetch-vietnam.sh [YYYYMMDD]   (mặc định: bản build mới nhất)
# Kết quả: infra/data/tiles/{vietnam.pmtiles, fonts/, sprites/}
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=data/tiles
BIN=data/tools
PMTILES_VERSION=1.31.2
ASSETS_REF=main
# Việt Nam đất liền + Hoàng Sa, Trường Sa.
BBOX="102.0,6.0,118.0,23.5"
mkdir -p "$OUT" "$BIN"

arch=$(uname -m); [[ $arch == aarch64 ]] && arch=arm64
if [[ ! -x $BIN/pmtiles ]]; then
  curl -sSL "https://github.com/protomaps/go-pmtiles/releases/download/v${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION}_Linux_${arch}.tar.gz" \
    | tar -xz -C "$BIN" pmtiles
fi

BUILD=${1:-$(curl -s https://build-metadata.protomaps.dev/builds.json \
  | python3 -c "import sys,json; print(json.load(sys.stdin)[-1]['key'].removesuffix('.pmtiles'))")}
echo "Cắt vùng Việt Nam từ bản build $BUILD ..."
"$BIN/pmtiles" extract "https://build.protomaps.com/${BUILD}.pmtiles" "$OUT/vietnam.pmtiles.tmp" --bbox="$BBOX"
mv "$OUT/vietnam.pmtiles.tmp" "$OUT/vietnam.pmtiles"

echo "Tải font và sprite ..."
tmp=$(mktemp -d)
curl -sSL "https://github.com/protomaps/basemaps-assets/archive/refs/heads/${ASSETS_REF}.tar.gz" | tar -xz -C "$tmp"
rm -rf "$OUT/fonts" "$OUT/sprites"
mv "$tmp"/basemaps-assets-*/fonts "$tmp"/basemaps-assets-*/sprites "$OUT/"
rm -rf "$tmp"
"$BIN/pmtiles" show "$OUT/vietnam.pmtiles" | head -20
echo "Xong: $OUT"
