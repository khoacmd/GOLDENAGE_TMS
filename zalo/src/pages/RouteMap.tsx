import 'maplibre-gl/dist/maplibre-gl.css'

import { layers, namedFlavor } from '@protomaps/basemaps'
import type { components } from '@tms/api-client'
import * as maplibregl from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { Protocol } from 'pmtiles'
import { useEffect, useRef } from 'react'

// openapi-fetch trả tuple thành mảng thường.
type Route = Omit<components['schemas']['CustomerRoute'], 'segments'> & { segments: number[][][] }

// MapLibre tự tính URL worker từ import.meta.url của chính nó - sai khi Vite đóng gói lại.
maplibregl.setWorkerUrl(workerUrl)
maplibregl.addProtocol('pmtiles', new Protocol().tile)

const BASE = new URL(`${import.meta.env.VITE_API_URL ?? ''}/tiles`, window.location.href).href
const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  glyphs: `${BASE}/fonts/{fontstack}/{range}.pbf`,
  sprite: `${BASE}/sprites/v4/light`,
  sources: {
    protomaps: {
      type: 'vector',
      url: `pmtiles://${BASE}/vietnam.pmtiles`,
      attribution: '© OpenStreetMap',
    },
  },
  layers: layers('protomaps', namedFlavor('light'), { lang: 'vi' }),
}

function marker(label: string, color: string): HTMLElement {
  const el = document.createElement('div')
  el.textContent = label
  el.className = 'map-marker'
  el.style.background = color
  return el
}

/** Tuyến xe đã đi: chỉ có kho, điểm giao của khách và các đoạn đường (đã cắt quanh điểm dừng khác). */
export default function RouteMap({ route }: { route: Route }) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!container.current) return
    const { warehouse, destination, segments } = route
    const bounds = new maplibregl.LngLatBounds()
    bounds.extend([warehouse.longitude, warehouse.latitude])
    bounds.extend([destination.longitude, destination.latitude])
    segments.forEach((segment) => segment.forEach(([lng, lat]) => bounds.extend([lng, lat])))

    const map = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      bounds,
      fitBoundsOptions: { padding: 40, maxZoom: 15 },
      attributionControl: { compact: true },
    })
    map.on('load', () => {
      map.addSource('route', {
        type: 'geojson',
        data: {
          type: 'Feature',
          properties: {},
          geometry: { type: 'MultiLineString', coordinates: segments },
        },
      })
      map.addLayer({
        id: 'route',
        type: 'line',
        source: 'route',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#006af5', 'line-width': 4 },
      })
    })
    new maplibregl.Marker({ element: marker('Kho', '#374151') })
      .setLngLat([warehouse.longitude, warehouse.latitude])
      .addTo(map)
    new maplibregl.Marker({ element: marker('Bạn', '#15803d') })
      .setLngLat([destination.longitude, destination.latitude])
      .addTo(map)
    return () => map.remove()
  }, [route])

  return <div ref={container} className="map" />
}
