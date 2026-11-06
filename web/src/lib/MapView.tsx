import 'maplibre-gl/dist/maplibre-gl.css'

import * as maplibregl from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { layers, namedFlavor } from '@protomaps/basemaps'
import { Protocol } from 'pmtiles'
import { useEffect, useRef, useState } from 'react'

// MapLibre tự tính URL worker từ import.meta.url của chính nó - sai khi Vite đóng gói lại.
maplibregl.setWorkerUrl(workerUrl)

export interface MapRoute {
  id: string
  color: string
  coords: [number, number][] // [lng, lat]
  dashed?: boolean // nét đứt = nối thẳng giữa các điểm (chưa có tuyến theo đường)
}

export interface MapZone {
  code: string
  name: string
  boundary: Record<string, unknown> // GeoJSON Polygon
}

export interface MapMarker {
  id: string
  lat: number
  lng: number
  label: string
  color?: string
  title?: string
}

/** Điểm vẽ thành lớp GeoJSON có gom cụm - dùng khi nhiều điểm (vd. bản đồ khách hàng). */
export interface MapPoint {
  id: string
  lat: number
  lng: number
  title: string
  description?: string
  color?: string
}

const TILES_BASE = import.meta.env.VITE_MAP_TILES_BASE ?? '/tiles'
const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    base: {
      type: 'raster',
      tiles: [import.meta.env.VITE_MAP_TILE_URL ?? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap',
    },
  },
  layers: [{ id: 'base', type: 'raster', source: 'base' }],
}

maplibregl.addProtocol('pmtiles', new Protocol().tile)

/**
 * Bản đồ tự host (PMTiles Việt Nam, xem infra/tiles); chưa có dữ liệu thì dùng tile OSM công cộng.
 * `VITE_MAP_TILE_URL` (tile raster) buộc dùng nguồn raster đó.
 */
const styleReady: Promise<maplibregl.StyleSpecification> = (async () => {
  if (import.meta.env.VITE_MAP_TILE_URL) return OSM_STYLE
  const base = new URL(TILES_BASE, window.location.href).href.replace(/\/$/, '')
  const ok = await fetch(`${base}/vietnam.pmtiles`, { method: 'HEAD' })
    .then((r) => r.ok && !r.headers.get('content-type')?.includes('text/html'))
    .catch(() => false)
  if (!ok) {
    console.warn('Chưa có bản đồ tự host, dùng tile OSM công cộng')
    return OSM_STYLE
  }
  return {
    version: 8,
    glyphs: `${base}/fonts/{fontstack}/{range}.pbf`,
    sprite: `${base}/sprites/v4/light`,
    sources: {
      protomaps: {
        type: 'vector',
        url: `pmtiles://${base}/vietnam.pmtiles`,
        attribution: '© OpenStreetMap',
      },
    },
    layers: layers('protomaps', namedFlavor('light'), { lang: 'vi' }),
  }
})()

const HANOI: [number, number] = [105.83, 21.02]

/**
 * Bản đồ hiển thị điểm (đánh số) + đường nối theo thứ tự `route`/`routes` (thẳng nét đứt, hoặc theo
 * đường thực tế khi `dashed: false` - xem `useTripRoads`).
 * `onPick` bật chế độ chọn tọa độ bằng click.
 */
export function MapView({
  markers,
  points,
  onPointAction,
  pointActionLabel = 'Sửa',
  route,
  routes,
  zones,
  height = 420,
  onPick,
}: {
  markers: MapMarker[]
  /** Nhiều điểm (hàng trăm - nghìn): gom cụm khi thu nhỏ, bấm vào điểm hiện thông tin. */
  points?: MapPoint[]
  /** Nút trong khung thông tin của điểm (vd. mở form sửa). */
  onPointAction?: (id: string) => void
  pointActionLabel?: string
  route?: [number, number][]
  /** Nhiều tuyến, mỗi tuyến 1 màu (vd. các chuyến của kế hoạch ngày). */
  routes?: MapRoute[]
  /** Vùng hạn chế lưu hành, vẽ dưới các tuyến. */
  zones?: MapZone[]
  height?: number
  onPick?: (lat: number, lng: number) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const markerRefs = useRef<maplibregl.Marker[]>([])
  const pickRef = useRef(onPick)
  const pointActionRef = useRef(onPointAction)
  const centered = useRef(false)
  const pointsFitted = useRef<MapPoint[] | null>(null)
  const [style, setStyle] = useState<maplibregl.StyleSpecification | null>(null)
  useEffect(() => {
    pickRef.current = onPick
    pointActionRef.current = onPointAction
  }, [onPick, onPointAction])
  useEffect(() => {
    let active = true
    void styleReady.then((s) => active && setStyle(s))
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!container.current) return
    if (!style) return
    const m = new maplibregl.Map({ container: container.current, style, center: HANOI, zoom: 11 })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }))
    m.on('click', (e: maplibregl.MapMouseEvent) => pickRef.current?.(e.lngLat.lat, e.lngLat.lng))
    map.current = m
    // Khung chứa có thể đổi kích thước sau khi tạo (card/tab vừa hiện) → vẽ lại cho đúng.
    const observer = new ResizeObserver(() => m.resize())
    observer.observe(container.current)
    return () => {
      observer.disconnect()
      m.remove()
      map.current = null
    }
  }, [style])

  useEffect(() => {
    const m = map.current
    if (!m) return
    markerRefs.current.forEach((mk) => mk.remove())
    markerRefs.current = markers.map((mk) => {
      const el = document.createElement('div')
      el.textContent = mk.label
      el.title = mk.title ?? ''
      Object.assign(el.style, {
        background: mk.color ?? '#1677ff',
        color: '#fff',
        borderRadius: '12px',
        padding: '2px 7px',
        fontSize: '12px',
        fontWeight: '600',
        border: '2px solid #fff',
        boxShadow: '0 1px 4px rgba(0,0,0,.4)',
        whiteSpace: 'nowrap',
      })
      return new maplibregl.Marker({ element: el }).setLngLat([mk.lng, mk.lat]).addTo(m)
    })

    const drawRoute = () => {
      const zoneData = {
        type: 'FeatureCollection',
        features: (zones ?? []).map((z) => ({
          type: 'Feature',
          properties: { name: z.name },
          geometry: z.boundary,
        })),
      } as maplibregl.GeoJSONSourceSpecification['data']
      const zoneSource = m.getSource('zones') as maplibregl.GeoJSONSource | undefined
      if (zoneSource) zoneSource.setData(zoneData)
      else {
        m.addSource('zones', { type: 'geojson', data: zoneData })
        m.addLayer({ id: 'zones-fill', type: 'fill', source: 'zones', paint: { 'fill-color': '#fa8c16', 'fill-opacity': 0.06 } })
        m.addLayer({
          id: 'zones-line',
          type: 'line',
          source: 'zones',
          paint: { 'line-color': '#fa8c16', 'line-width': 2, 'line-dasharray': [3, 2] },
        })
      }
      const lines = routes ?? (route ? [{ id: 'route', color: '#1677ff', coords: route }] : [])
      const data: maplibregl.GeoJSONSourceSpecification['data'] = {
        type: 'FeatureCollection',
        features: lines.map((r) => ({
          type: 'Feature',
          properties: { color: r.color, dashed: r.dashed ?? true },
          geometry: { type: 'LineString', coordinates: r.coords },
        })),
      }
      const source = m.getSource('route') as maplibregl.GeoJSONSource | undefined
      if (source) source.setData(data)
      else {
        m.addSource('route', { type: 'geojson', data })
        // line-dasharray không nhận biểu thức theo feature → 2 lớp lọc theo `dashed`.
        m.addLayer({
          id: 'route',
          type: 'line',
          source: 'route',
          filter: ['==', ['get', 'dashed'], true],
          paint: { 'line-color': ['get', 'color'], 'line-width': 3, 'line-dasharray': [2, 1] },
        })
        m.addLayer({
          id: 'route-road',
          type: 'line',
          source: 'route',
          filter: ['==', ['get', 'dashed'], false],
          layout: { 'line-join': 'round', 'line-cap': 'round' },
          paint: { 'line-color': ['get', 'color'], 'line-width': 4, 'line-opacity': 0.85 },
        })
      }
    }
    if (m.isStyleLoaded()) drawRoute()
    else m.once('load', drawRoute)

    // Đang chọn tọa độ: chỉ căn giữa lần đầu, giữ nguyên khung nhìn sau mỗi lần bấm.
    if (pickRef.current && centered.current) return
    centered.current = true
    if (markers.length === 1) m.jumpTo({ center: [markers[0].lng, markers[0].lat], zoom: 14 })
    else if (markers.length > 1) {
      const bounds = new maplibregl.LngLatBounds()
      markers.forEach((mk) => bounds.extend([mk.lng, mk.lat]))
      m.fitBounds(bounds, { padding: 50, maxZoom: 15, duration: 0 })
    }
  }, [markers, route, routes, zones, style])

  useEffect(() => {
    const m = map.current
    if (!m || !style || !points) return
    const data: maplibregl.GeoJSONSourceSpecification['data'] = {
      type: 'FeatureCollection',
      features: points.map((p) => ({
        type: 'Feature',
        properties: { id: p.id, title: p.title, description: p.description ?? '', color: p.color ?? '#1677ff' },
        geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
      })),
    }
    const draw = () => {
      const source = m.getSource('points') as maplibregl.GeoJSONSource | undefined
      if (source) source.setData(data)
      else {
        m.addSource('points', { type: 'geojson', data, cluster: true, clusterRadius: 40, clusterMaxZoom: 14 })
        m.addLayer({
          id: 'points-cluster',
          type: 'circle',
          source: 'points',
          filter: ['has', 'point_count'],
          paint: {
            'circle-color': '#1677ff',
            'circle-opacity': 0.85,
            'circle-radius': ['step', ['get', 'point_count'], 14, 10, 18, 50, 24, 200, 30],
            'circle-stroke-width': 2,
            'circle-stroke-color': '#fff',
          },
        })
        // Tile OSM dự phòng không có font (glyphs) → chỉ vẽ số lượng khi style có.
        if (style.glyphs) {
          m.addLayer({
            id: 'points-count',
            type: 'symbol',
            source: 'points',
            filter: ['has', 'point_count'],
            layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12, 'text-font': ['Noto Sans Medium'] },
            paint: { 'text-color': '#fff' },
          })
        }
        m.addLayer({
          id: 'points',
          type: 'circle',
          source: 'points',
          filter: ['!', ['has', 'point_count']],
          paint: {
            'circle-color': ['get', 'color'],
            'circle-radius': 7,
            'circle-stroke-width': 2,
            'circle-stroke-color': '#fff',
          },
        })
        m.on('click', 'points-cluster', (e) => {
          const feature = e.features?.[0]
          if (!feature) return
          const clusterId = feature.properties.cluster_id as number
          void (m.getSource('points') as maplibregl.GeoJSONSource)
            .getClusterExpansionZoom(clusterId)
            .then((zoom) => m.easeTo({ center: (feature.geometry as { coordinates: [number, number] }).coordinates, zoom }))
        })
        m.on('click', 'points', (e) => {
          const feature = e.features?.[0]
          if (!feature) return
          const props = feature.properties as { id: string; title: string; description: string }
          // Dựng DOM bằng textContent: tên/địa chỉ là dữ liệu người dùng nhập.
          const box = document.createElement('div')
          const title = document.createElement('div')
          title.textContent = props.title
          title.style.fontWeight = '600'
          box.append(title)
          if (props.description) {
            const desc = document.createElement('div')
            desc.textContent = props.description
            box.append(desc)
          }
          if (pointActionRef.current) {
            const action = document.createElement('a')
            action.textContent = pointActionLabel
            action.href = '#'
            action.onclick = (ev) => {
              ev.preventDefault()
              pointActionRef.current?.(props.id)
            }
            box.append(action)
          }
          new maplibregl.Popup({ closeButton: true, maxWidth: '280px' })
            .setLngLat((feature.geometry as { coordinates: [number, number] }).coordinates)
            .setDOMContent(box)
            .addTo(m)
        })
        for (const layer of ['points', 'points-cluster']) {
          m.on('mouseenter', layer, () => (m.getCanvas().style.cursor = 'pointer'))
          m.on('mouseleave', layer, () => (m.getCanvas().style.cursor = ''))
        }
      }
      // Căn khung theo các điểm khi tập điểm đổi (lọc lại), không phải mỗi lần vẽ.
      if (pointsFitted.current !== points && points.length > 0) {
        pointsFitted.current = points
        const bounds = new maplibregl.LngLatBounds()
        points.forEach((p) => bounds.extend([p.lng, p.lat]))
        m.fitBounds(bounds, { padding: 40, maxZoom: 15, duration: 0 })
      }
    }
    if (m.isStyleLoaded()) draw()
    else m.once('load', draw)
  }, [points, style, pointActionLabel])

  return <div ref={container} style={{ height, width: '100%', borderRadius: 8, overflow: 'hidden' }} />
}
