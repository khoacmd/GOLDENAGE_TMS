import 'maplibre-gl/dist/maplibre-gl.css'

import * as maplibregl from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { layers, namedFlavor } from '@protomaps/basemaps'
import { Protocol } from 'pmtiles'
import { useEffect, useRef, useState } from 'react'

// MapLibre tự tính URL worker từ import.meta.url của chính nó - sai khi Vite đóng gói lại.
maplibregl.setWorkerUrl(workerUrl)

export interface MapMarker {
  id: string
  lat: number
  lng: number
  label: string
  color?: string
  title?: string
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
 * Bản đồ hiển thị điểm (đánh số) + đường nối theo thứ tự `route` (đường thẳng; định tuyến thật ở M4).
 * `onPick` bật chế độ chọn tọa độ bằng click.
 */
export function MapView({
  markers,
  route,
  height = 420,
  onPick,
}: {
  markers: MapMarker[]
  route?: [number, number][]
  height?: number
  onPick?: (lat: number, lng: number) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const markerRefs = useRef<maplibregl.Marker[]>([])
  const pickRef = useRef(onPick)
  const [style, setStyle] = useState<maplibregl.StyleSpecification | null>(null)
  useEffect(() => {
    pickRef.current = onPick
  }, [onPick])
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
    return () => {
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
      const data: maplibregl.GeoJSONSourceSpecification['data'] = {
        type: 'Feature',
        properties: {},
        geometry: { type: 'LineString', coordinates: route ?? [] },
      }
      const source = m.getSource('route') as maplibregl.GeoJSONSource | undefined
      if (source) source.setData(data)
      else {
        m.addSource('route', { type: 'geojson', data })
        m.addLayer({
          id: 'route',
          type: 'line',
          source: 'route',
          paint: { 'line-color': '#1677ff', 'line-width': 3, 'line-dasharray': [2, 1] },
        })
      }
    }
    if (m.isStyleLoaded()) drawRoute()
    else m.once('load', drawRoute)

    if (markers.length === 1) m.jumpTo({ center: [markers[0].lng, markers[0].lat], zoom: 14 })
    else if (markers.length > 1) {
      const bounds = new maplibregl.LngLatBounds()
      markers.forEach((mk) => bounds.extend([mk.lng, mk.lat]))
      m.fitBounds(bounds, { padding: 50, maxZoom: 15, duration: 0 })
    }
  }, [markers, route, style])

  return <div ref={container} style={{ height, width: '100%', borderRadius: 8, overflow: 'hidden' }} />
}
