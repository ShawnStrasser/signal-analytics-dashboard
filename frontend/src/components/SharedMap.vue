<template>
  <div ref="mapContainer" style="height: 100%; width: 100%;"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import L from 'leaflet'
import { useGeometryStore } from '@/stores/geometry'
import { useMapStateStore } from '@/stores/mapState'
import { travelTimeColorScale, anomalyColorScale } from '@/utils/colorScale'

const props = defineProps({
  signals: {
    type: Array,
    default: () => []
  },
  dataType: {
    type: String,
    default: 'travel-time', // 'travel-time' or 'anomaly'
    validator: (value) => ['travel-time', 'anomaly'].includes(value)
  },
  anomalyType: {
    type: String,
    default: 'All'
  }
})

const emit = defineEmits(['signal-selected'])

const mapContainer = ref(null)
let map = null
let markersLayer = null
let geometryLayer = null

const geometryStore = useGeometryStore()
const mapStateStore = useMapStateStore()
const { featureCollection } = storeToRefs(geometryStore)

onMounted(() => {
  initializeMap()
  updateMarkers()
  geometryStore.loadGeometry().catch(error => {
    console.error('Failed to preload XD geometry:', error)
  })
})

onUnmounted(() => {
  if (map) {
    // Save map state before unmounting
    const center = map.getCenter()
    const zoom = map.getZoom()
    mapStateStore.updateMapState([center.lat, center.lng], zoom)
    
    map.remove()
    map = null
  }
  geometryLayer = null
  markersLayer = null
})

watch(() => [props.signals, props.anomalyType], () => {
  updateMarkers()
}, { deep: true })

watch(featureCollection, () => {
  updateGeometry()
  updateMarkers()
}, { deep: true })

function initializeMap() {
  // Use saved map state or defaults
  const savedCenter = mapStateStore.mapCenter
  const savedZoom = mapStateStore.mapZoom

  map = L.map(mapContainer.value).setView(savedCenter, savedZoom)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
  }).addTo(map)

  geometryLayer = L.geoJSON(null, {
    style: () => ({
      color: '#1f78b4',
      weight: 2,
      opacity: 0.7,
      fillOpacity: 0.1
    }),
    onEachFeature: (feature, layer) => {
      if (feature?.properties?.XD) {
        layer.bindPopup(`<div><strong>XD Segment:</strong> ${feature.properties.XD}</div>`)
      }
    }
  }).addTo(map)

  markersLayer = L.layerGroup().addTo(map)

  // Save map state when user moves/zooms
  map.on('moveend', () => {
    const center = map.getCenter()
    const zoom = map.getZoom()
    mapStateStore.updateMapState([center.lat, center.lng], zoom)
  })

  updateGeometry()
}

function updateGeometry() {
  if (!map || !geometryLayer) return

  geometryLayer.clearLayers()

  const collection = featureCollection.value
  if (!collection || !Array.isArray(collection.features) || collection.features.length === 0) {
    return
  }

  geometryLayer.addData(collection)
}

function updateMarkers() {
  if (!map || !markersLayer) return
  
  markersLayer.clearLayers()
  
  if (props.signals.length === 0) return

  const bounds = []
  
  if (props.dataType === 'anomaly') {
    // Anomaly mode: filter signals with anomalies and color by count
    const countColumn = props.anomalyType === "Point Source" ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
    const signalsWithAnomalies = props.signals.filter(signal => (signal[countColumn] || 0) > 0)
    
    if (signalsWithAnomalies.length === 0) return

    const maxCount = Math.max(...signalsWithAnomalies.map(s => s[countColumn] || 0))
    const minCount = Math.min(...signalsWithAnomalies.map(s => s[countColumn] || 0))
    
    signalsWithAnomalies.forEach(signal => {
      if (!signal.LATITUDE || !signal.LONGITUDE) return
      
      bounds.push([signal.LATITUDE, signal.LONGITUDE])
      
      const count = signal[countColumn] || 0
      
      // Calculate bubble size
      let radius
      if (maxCount > minCount) {
        radius = 15 + ((count - minCount) / (maxCount - minCount)) * 35
      } else {
        radius = 25
      }
      
      // Color using anomaly color scale
      const color = anomalyColorScale(count, maxCount)
      
      const marker = L.circleMarker([signal.LATITUDE, signal.LONGITUDE], {
        radius: radius,
        fillColor: color,
        color: color,
        weight: 2,
        opacity: 0.8,
        fillOpacity: 0.6
      })
      
      const popupContent = `
        <div>
          <h4>Signal ${signal.ID}</h4>
          <p><strong>Total Anomalies:</strong> ${signal.ANOMALY_COUNT || 0}</p>
          <p><strong>Point Source Anomalies:</strong> ${signal.POINT_SOURCE_COUNT || 0}</p>
          <p><strong>Approach:</strong> ${signal.APPROACH || 'N/A'}</p>
          <p><strong>Valid Geometry:</strong> ${signal.VALID_GEOMETRY === 1 ? 'Yes' : 'No'}</p>
        </div>
      `
      
      marker.bindPopup(popupContent)
      marker.on('click', () => {
        emit('signal-selected', signal.ID)
      })
      
      markersLayer.addLayer(marker)
    })
    
  } else {
    // Travel time mode: show all signals, color by average travel time
    const totals = props.signals.map(signal => Number(signal.TOTAL_TRAVEL_TIME ?? signal.TOTAL_TRAVEL_TIME_SECONDS ?? 0))
    const validTotals = totals.filter(value => Number.isFinite(value))
    const maxTravelTime = validTotals.length ? Math.max(...validTotals) : 0
    const minTravelTime = validTotals.length ? Math.min(...validTotals) : 0
    
    props.signals.forEach(signal => {
      const latitude = Number(signal.LATITUDE)
      const longitude = Number(signal.LONGITUDE)

      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return
      
      bounds.push([latitude, longitude])
      
      // Calculate bubble size based on total travel time
      const totalTravelTime = Number(signal.TOTAL_TRAVEL_TIME ?? signal.TOTAL_TRAVEL_TIME_SECONDS ?? 0) || 0
      
      let radius
      if (maxTravelTime > minTravelTime) {
        radius = 10 + ((totalTravelTime - minTravelTime) / (maxTravelTime - minTravelTime)) * 30
      } else {
        radius = 20
      }
      
      // Color using travel time color scale based on average
      const avgTime = Number(signal.AVG_TRAVEL_TIME ?? signal.AVG_TRAVEL_TIME_SECONDS ?? 0) || 0
      const color = travelTimeColorScale(avgTime)
      
      const marker = L.circleMarker([latitude, longitude], {
        radius: radius,
        fillColor: color,
        color: color,
        weight: 2,
        opacity: 0.8,
        fillOpacity: 0.6
      })
      
      const totalTravelTimeDisplay = Number.isFinite(totalTravelTime) ? totalTravelTime.toFixed(0) : 'N/A'
      const avgTravelTimeDisplay = Number.isFinite(avgTime) ? avgTime.toFixed(1) : 'N/A'
      const recordCount = Number(signal.RECORD_COUNT ?? 0) || 0

      const popupContent = `
        <div>
          <h4>Signal ${signal.ID}</h4>
          <p><strong>Total Travel Time:</strong> ${totalTravelTimeDisplay}s</p>
          <p><strong>Average Travel Time:</strong> ${avgTravelTimeDisplay}s</p>
          <p><strong>Records:</strong> ${recordCount}</p>
          <p><strong>Approach:</strong> ${signal.APPROACH || 'N/A'}</p>
        </div>
      `
      
      marker.bindPopup(popupContent)
      marker.on('click', () => {
        emit('signal-selected', signal.ID)
      })
      
      markersLayer.addLayer(marker)
    })
  }
  
  // Fit map to bounds only if this is the initial load (low zoom level)
  let mapBounds = null
  if (bounds.length > 0) {
    mapBounds = L.latLngBounds(bounds)
  }

  if (geometryLayer && geometryLayer.getLayers().length > 0) {
    const geometryBounds = geometryLayer.getBounds()
    if (geometryBounds.isValid()) {
      mapBounds = mapBounds ? mapBounds.extend(geometryBounds) : geometryBounds
    }
  }

  // Only auto-fit on initial load (when zoom is at default level)
  if (mapBounds && mapBounds.isValid() && map.getZoom() <= 7) {
    map.fitBounds(mapBounds, { padding: [20, 20] })
  }
}
</script>
