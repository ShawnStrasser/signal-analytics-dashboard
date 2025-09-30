<template>
  <div ref="mapContainer" style="height: 100%; width: 100%;"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { storeToRefs } from 'pinia'
import L from 'leaflet'
import { useGeometryStore } from '@/stores/geometry'
import { useMapStateStore } from '@/stores/mapState'
import { useSelectionStore } from '@/stores/selection'
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

const emit = defineEmits(['selection-changed'])

const mapContainer = ref(null)
let map = null
let signalMarkers = new Map() // Map signal ID to marker
let xdLayers = new Map() // Map XD to layer
let markersLayer = null
let geometryLayer = null

const geometryStore = useGeometryStore()
const mapStateStore = useMapStateStore()
const selectionStore = useSelectionStore()
const { featureCollection } = storeToRefs(geometryStore)
const { selectedSignalsList, selectedXdSegmentsList } = storeToRefs(selectionStore)

// Marker radius in meters (real-world distance)
// This will scale with the map automatically, just like XD segments
const SIGNAL_RADIUS_METERS = 60 // About 197 feet

onMounted(() => {
  initializeMap()
  updateMarkers()
  updateGeometry()
  geometryStore.loadGeometry().catch(error => {
    console.error('Failed to preload XD geometry:', error)
  })

  // Update mappings when signals load
  if (props.signals.length > 0) {
    selectionStore.updateMappings(props.signals)
    // Zoom to fit initial data
    autoZoomToSignals()
  }
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
  signalMarkers.clear()
  xdLayers.clear()
})

// Watch for signal data changes
watch(() => props.signals, (newSignals) => {
  console.log('🔄 WATCH: props.signals changed', {
    signalCount: newSignals.length,
    currentZoom: map?.getZoom(),
    xdLayersCount: xdLayers.size,
    signalMarkersCount: signalMarkers.size
  })

  const t0 = performance.now()
  if (newSignals.length > 0) {
    selectionStore.updateMappings(newSignals)
  }

  const t1 = performance.now()
  console.log(`⏱️ updateMappings: ${(t1 - t0).toFixed(2)}ms`)

  updateMarkers()
  const t2 = performance.now()
  console.log(`⏱️ updateMarkers: ${(t2 - t1).toFixed(2)}ms`)

  updateGeometry() // Update geometry to reflect filtered state
  const t3 = performance.now()
  console.log(`⏱️ updateGeometry: ${(t3 - t2).toFixed(2)}ms`)

  autoZoomToSignals() // Zoom after both markers and geometry are updated
  const t4 = performance.now()
  console.log(`⏱️ autoZoomToSignals: ${(t4 - t3).toFixed(2)}ms`)
  console.log(`⏱️ TOTAL: ${(t4 - t0).toFixed(2)}ms`)
}, { deep: true })

// Watch for anomaly type changes
watch(() => props.anomalyType, () => {
  updateMarkers()
})

// Watch for geometry changes
watch(featureCollection, () => {
  updateGeometry()
}, { deep: true })

// Watch for selection changes to update styling
watch([selectedSignalsList, selectedXdSegmentsList], () => {
  updateSelectionStyles()
}, { deep: true })

function initializeMap() {
  // Use saved map state or defaults
  const savedCenter = mapStateStore.mapCenter
  const savedZoom = mapStateStore.mapZoom

  map = L.map(mapContainer.value, {
    // Remove focus outline on click
    keyboard: false
  }).setView(savedCenter, savedZoom)

  // Use CartoDB Positron (grayscale) basemap for better contrast
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors, © CartoDB',
    maxZoom: 19
  }).addTo(map)

  // Create layers - ORDER MATTERS: geometry on top of markers
  markersLayer = L.layerGroup().addTo(map)
  geometryLayer = L.geoJSON(null, {
    style: () => ({
      color: '#1f78b4',
      weight: 1,
      opacity: 0.7,
      fillOpacity: 0.3
    })
  }).addTo(map)

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

  console.log('🗺️ updateGeometry: START', {
    xdLayersBeforeClear: xdLayers.size
  })

  geometryLayer.clearLayers()
  xdLayers.clear()

  const collection = featureCollection.value
  if (!collection || !Array.isArray(collection.features) || collection.features.length === 0) {
    console.log('🗺️ updateGeometry: NO FEATURES')
    return
  }

  // Build set of XD values from currently displayed signals
  // This will be used to determine which XD segments should be colored vs greyed out
  const displayedXDs = new Set(props.signals.map(signal => signal.XD))
  console.log('🗺️ updateGeometry:', {
    totalFeatures: collection.features.length,
    displayedXDsCount: displayedXDs.size,
    displayedXDs: Array.from(displayedXDs)
  })

  // Get current data values for coloring
  const xdDataMap = getXdDataMap()

  collection.features.forEach(feature => {
    if (!feature.properties?.XD) return

    const xd = feature.properties.XD
    
    // Always render all XD segments, but grey out those not in current filter
    const isInFilteredSet = displayedXDs.has(xd)
    const dataValue = xdDataMap.get(xd)
    
    // Determine color based on data type and value
    let fillColor = '#cccccc' // default gray for no data or filtered out
    
    if (isInFilteredSet && dataValue !== undefined && dataValue !== null) {
      if (props.dataType === 'anomaly') {
        const countColumn = props.anomalyType === "Point Source" ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
        const count = dataValue[countColumn] || 0
        const maxCount = getMaxValue(xdDataMap, countColumn)
        fillColor = anomalyColorScale(count, maxCount)
      } else {
        // Travel time mode
        const avgTime = dataValue.AVG_TRAVEL_TIME || 0
        fillColor = travelTimeColorScale(avgTime)
      }
    }

    const isSelected = selectionStore.isXdSegmentSelected(xd)
    
    const layer = L.geoJSON(feature, {
      style: {
        color: isSelected ? '#000000' : (isInFilteredSet ? fillColor : '#808080'),
        weight: isSelected ? 3 : 1,
        opacity: isSelected ? 1 : (isInFilteredSet ? 0.8 : 0.3),
        fillColor: fillColor,
        fillOpacity: isInFilteredSet ? 0.6 : 0.2
      },
      onEachFeature: (feature, layer) => {
        // Tooltip on hover
        const tooltipContent = createXdTooltip(xd, dataValue)
        layer.bindTooltip(tooltipContent, {
          sticky: true,
          direction: 'top'
        })

        // Click handler - only allow selection if in filtered set
        layer.on('click', (e) => {
          L.DomEvent.stopPropagation(e)
          if (isInFilteredSet) {
            selectionStore.toggleXdSegment(xd)
            emit('selection-changed')
          }
        })
      }
    })

    layer.addTo(geometryLayer)
    xdLayers.set(xd, layer)
  })
}

function getXdDataMap() {
  // Create a map of XD -> data values from signals
  const xdMap = new Map()
  
  props.signals.forEach(signal => {
    if (signal.XD !== undefined && signal.XD !== null) {
      // Accumulate data for XD segments (since multiple signals can map to same XD)
      if (!xdMap.has(signal.XD)) {
        xdMap.set(signal.XD, {
          ANOMALY_COUNT: 0,
          POINT_SOURCE_COUNT: 0,
          TOTAL_TRAVEL_TIME: 0,
          AVG_TRAVEL_TIME: 0,
          RECORD_COUNT: 0,
          count: 0
        })
      }
      
      const existing = xdMap.get(signal.XD)
      existing.ANOMALY_COUNT += (signal.ANOMALY_COUNT || 0)
      existing.POINT_SOURCE_COUNT += (signal.POINT_SOURCE_COUNT || 0)
      existing.TOTAL_TRAVEL_TIME += (signal.TOTAL_TRAVEL_TIME || signal.TOTAL_TRAVEL_TIME_SECONDS || 0)
      existing.AVG_TRAVEL_TIME += (signal.AVG_TRAVEL_TIME || signal.AVG_TRAVEL_TIME_SECONDS || 0)
      existing.RECORD_COUNT += (signal.RECORD_COUNT || 0)
      existing.count += 1
      
      // Average the AVG_TRAVEL_TIME
      existing.AVG_TRAVEL_TIME = existing.AVG_TRAVEL_TIME / existing.count
    }
  })
  
  return xdMap
}

function getMaxValue(xdMap, key) {
  let max = 0
  for (const value of xdMap.values()) {
    if (value[key] > max) max = value[key]
  }
  return max
}

function createXdTooltip(xd, dataValue) {
  if (!dataValue) {
    return `<div><strong>XD Segment:</strong> ${xd}<br><em>No data</em></div>`
  }
  
  if (props.dataType === 'anomaly') {
    return `
      <div>
        <strong>XD Segment:</strong> ${xd}<br>
        <strong>Total Anomalies:</strong> ${dataValue.ANOMALY_COUNT || 0}<br>
        <strong>Point Source:</strong> ${dataValue.POINT_SOURCE_COUNT || 0}
      </div>
    `
  } else {
    const totalTravelTime = dataValue.TOTAL_TRAVEL_TIME || 0
    return `
      <div>
        <strong>XD Segment:</strong> ${xd}<br>
        <strong>Total Travel Time:</strong> ${totalTravelTime.toFixed(0)}s<br>
        <strong>Records:</strong> ${dataValue.RECORD_COUNT || 0}
      </div>
    `
  }
}

function updateMarkers() {
  if (!map || !markersLayer) return
  
  markersLayer.clearLayers()
  signalMarkers.clear()
  
  if (props.signals.length === 0) return

  const bounds = []
  
  if (props.dataType === 'anomaly') {
    // Anomaly mode: show all signals, color by anomaly count
    const countColumn = props.anomalyType === "Point Source" ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
    const signalsWithData = props.signals.filter(signal => (signal[countColumn] || 0) >= 0)
    
    if (signalsWithData.length === 0) return

    // Group signals by ID to aggregate multiple XD segments per signal
    const signalGroups = new Map()
    signalsWithData.forEach(signal => {
      if (!signal.LATITUDE || !signal.LONGITUDE) return
      
      if (!signalGroups.has(signal.ID)) {
        signalGroups.set(signal.ID, {
          ID: signal.ID,
          LATITUDE: signal.LATITUDE,
          LONGITUDE: signal.LONGITUDE,
          APPROACH: signal.APPROACH,
          VALID_GEOMETRY: signal.VALID_GEOMETRY,
          ANOMALY_COUNT: 0,
          POINT_SOURCE_COUNT: 0
        })
      }
      
      const group = signalGroups.get(signal.ID)
      group.ANOMALY_COUNT += (signal.ANOMALY_COUNT || 0)
      group.POINT_SOURCE_COUNT += (signal.POINT_SOURCE_COUNT || 0)
    })

    const aggregatedSignals = Array.from(signalGroups.values())
    const counts = aggregatedSignals.map(s => s[countColumn] || 0)
    const maxCount = Math.max(...counts, 1)
    
    aggregatedSignals.forEach(signal => {
      bounds.push([signal.LATITUDE, signal.LONGITUDE])
      
      const count = signal[countColumn] || 0
      
      // Color using anomaly color scale
      const color = anomalyColorScale(count, maxCount)
      
      const isSelected = selectionStore.isSignalSelected(signal.ID)
      
      const marker = L.circle([signal.LATITUDE, signal.LONGITUDE], SIGNAL_RADIUS_METERS, {
        fillColor: color,
        color: isSelected ? '#000000' : '#FFFFFF',
        weight: isSelected ? 3 : 1,
        opacity: isSelected ? 1 : 0.5,
        fillOpacity: 0.8,
        interactive: true,
        bubblingMouseEvents: false
      })
      
      const tooltipContent = `
        <div>
          <h4>Signal ${signal.ID}</h4>
          <p><strong>Total Anomalies:</strong> ${signal.ANOMALY_COUNT || 0}</p>
          <p><strong>Point Source:</strong> ${signal.POINT_SOURCE_COUNT || 0}</p>
          <p><strong>Approach:</strong> ${signal.APPROACH ? 'Yes' : 'No'}</p>
          <p><strong>Valid Geometry:</strong> ${signal.VALID_GEOMETRY === 1 || signal.VALID_GEOMETRY === true ? 'Yes' : 'No'}</p>
        </div>
      `
      
      marker.bindTooltip(tooltipContent, {
        direction: 'top',
        offset: [0, -10]
      })
      
      marker.on('click', (e) => {
        L.DomEvent.stopPropagation(e)
        selectionStore.toggleSignal(signal.ID)
        emit('selection-changed')
      })
      
      markersLayer.addLayer(marker)
      signalMarkers.set(signal.ID, marker)
    })
    
  } else {
    // Travel time mode: group signals by ID first, then aggregate
    const signalGroups = new Map()
    
    props.signals.forEach(signal => {
      const latitude = Number(signal.LATITUDE)
      const longitude = Number(signal.LONGITUDE)

      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return
      
      if (!signalGroups.has(signal.ID)) {
        signalGroups.set(signal.ID, {
          ID: signal.ID,
          LATITUDE: latitude,
          LONGITUDE: longitude,
          APPROACH: signal.APPROACH,
          VALID_GEOMETRY: signal.VALID_GEOMETRY,
          TOTAL_TRAVEL_TIME: 0,
          RECORD_COUNT: 0,
          totalForAvg: 0,
          countForAvg: 0
        })
      }
      
      const group = signalGroups.get(signal.ID)
      const totalTime = Number(signal.TOTAL_TRAVEL_TIME ?? signal.TOTAL_TRAVEL_TIME_SECONDS ?? 0) || 0
      const records = Number(signal.RECORD_COUNT ?? 0) || 0
      const avgTime = Number(signal.AVG_TRAVEL_TIME ?? signal.AVG_TRAVEL_TIME_SECONDS ?? 0) || 0
      
      group.TOTAL_TRAVEL_TIME += totalTime
      group.RECORD_COUNT += records
      
      // For weighted average calculation
      if (records > 0 && avgTime > 0) {
        group.totalForAvg += avgTime * records
        group.countForAvg += records
      }
    })
    
    const aggregatedSignals = Array.from(signalGroups.values())
    
    // Calculate max for color scaling
    const totals = aggregatedSignals.map(signal => signal.TOTAL_TRAVEL_TIME)
    const validTotals = totals.filter(value => Number.isFinite(value))
    const maxTravelTime = validTotals.length ? Math.max(...validTotals) : 0
    
    aggregatedSignals.forEach(signal => {
      bounds.push([signal.LATITUDE, signal.LONGITUDE])
      
      // Calculate weighted average for color
      const avgTime = signal.countForAvg > 0 
        ? signal.totalForAvg / signal.countForAvg 
        : 0
      const color = travelTimeColorScale(avgTime)
      
      const isSelected = selectionStore.isSignalSelected(signal.ID)
      
      const marker = L.circle([signal.LATITUDE, signal.LONGITUDE], SIGNAL_RADIUS_METERS, {
        fillColor: color,
        color: isSelected ? '#000000' : '#FFFFFF',
        weight: isSelected ? 3 : 1,
        opacity: isSelected ? 1 : 0.5,
        fillOpacity: 0.8,
        interactive: true,
        bubblingMouseEvents: false
      })
      
      const totalTravelTime = signal.TOTAL_TRAVEL_TIME
      const totalTravelTimeDisplay = Number.isFinite(totalTravelTime) ? totalTravelTime.toFixed(0) : 'N/A'
      const recordCount = signal.RECORD_COUNT

      const tooltipContent = `
        <div>
          <h4>Signal ${signal.ID}</h4>
          <p><strong>Total Travel Time:</strong> ${totalTravelTimeDisplay}s</p>
          <p><strong>Records:</strong> ${recordCount}</p>
          <p><strong>Approach:</strong> ${signal.APPROACH ? 'Yes' : 'No'}</p>
        </div>
      `
      
      marker.bindTooltip(tooltipContent, {
        direction: 'top',
        offset: [0, -10]
      })
      
      marker.on('click', (e) => {
        L.DomEvent.stopPropagation(e)
        selectionStore.toggleSignal(signal.ID)
        emit('selection-changed')
      })
      
      markersLayer.addLayer(marker)
      signalMarkers.set(signal.ID, marker)
    })
  }
}

function autoZoomToSignals() {
  console.log('🔍 autoZoomToSignals: START', {
    hasMap: !!map,
    signalMarkersCount: signalMarkers.size,
    xdLayersCount: xdLayers.size,
    currentZoom: map?.getZoom()
  })

  if (!map || signalMarkers.size === 0) {
    console.log('🔍 autoZoomToSignals: SKIPPED (no map or markers)')
    return
  }

  const bounds = []
  signalMarkers.forEach((marker) => {
    bounds.push(marker.getLatLng())
  })

  console.log('🔍 autoZoomToSignals: marker bounds', {
    markerBoundsCount: bounds.length
  })

  if (bounds.length > 0) {
    const mapBounds = L.latLngBounds(bounds)
    const initialBounds = {
      north: mapBounds.getNorth(),
      south: mapBounds.getSouth(),
      east: mapBounds.getEast(),
      west: mapBounds.getWest()
    }
    console.log('🔍 autoZoomToSignals: initial bounds (markers only)', initialBounds)

    // Add bounds of ONLY the filtered XD segments
    // OPTIMIZATION: Only iterate through the XDs we care about, not all 16k layers
    const displayedXDs = new Set(props.signals.map(signal => signal.XD))
    let xdBoundsAdded = 0

    // Instead of iterating through all xdLayers, only check the ones we need
    displayedXDs.forEach(xd => {
      const layer = xdLayers.get(xd)
      if (layer) {
        const layerBounds = layer.getBounds()
        if (layerBounds.isValid()) {
          mapBounds.extend(layerBounds)
          xdBoundsAdded++
        }
      }
    })

    console.log('🔍 autoZoomToSignals: after adding XD bounds', {
      xdBoundsAdded,
      displayedXDsCount: displayedXDs.size,
      finalBounds: {
        north: mapBounds.getNorth(),
        south: mapBounds.getSouth(),
        east: mapBounds.getEast(),
        west: mapBounds.getWest()
      }
    })

    if (mapBounds.isValid()) {
      console.log('🔍 autoZoomToSignals: CALLING fitBounds')
      // Set maxZoom to 15 to prevent zooming in too far on single signals
      map.fitBounds(mapBounds, { padding: [50, 50], maxZoom: 15 })
      console.log('🔍 autoZoomToSignals: DONE, new zoom:', map.getZoom())
    } else {
      console.log('🔍 autoZoomToSignals: SKIPPED (invalid bounds)')
    }
  }
}

function updateSelectionStyles() {
  // Update signal marker styles
  signalMarkers.forEach((marker, signalId) => {
    const isSelected = selectionStore.isSignalSelected(signalId)
    const currentOptions = marker.options
    
    marker.setStyle({
      color: isSelected ? '#000000' : '#FFFFFF',
      weight: isSelected ? 3 : 1,
      opacity: isSelected ? 1 : 0.5
    })
  })
  
  // Build set of XD values from currently displayed signals
  const displayedXDs = new Set(props.signals.map(signal => signal.XD))
  
  // Update XD layer styles
  const xdDataMap = getXdDataMap()
  
  xdLayers.forEach((layer, xd) => {
    const isSelected = selectionStore.isXdSegmentSelected(xd)
    const isInFilteredSet = displayedXDs.has(xd)
    const dataValue = xdDataMap.get(xd)
    
    let fillColor = '#cccccc'
    
    if (isInFilteredSet && dataValue !== undefined && dataValue !== null) {
      if (props.dataType === 'anomaly') {
        const countColumn = props.anomalyType === "Point Source" ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
        const count = dataValue[countColumn] || 0
        const maxCount = getMaxValue(xdDataMap, countColumn)
        fillColor = anomalyColorScale(count, maxCount)
      } else {
        const avgTime = dataValue.AVG_TRAVEL_TIME || 0
        fillColor = travelTimeColorScale(avgTime)
      }
    }
    
    layer.setStyle({
      color: isSelected ? '#000000' : (isInFilteredSet ? fillColor : '#808080'),
      weight: isSelected ? 3 : 1,
      opacity: isSelected ? 1 : (isInFilteredSet ? 0.8 : 0.3),
      fillColor: fillColor,
      fillOpacity: isInFilteredSet ? (isSelected ? 0.7 : 0.6) : 0.2
    })
  })
}

// Function to rezoom map to fit current signal markers
function rezoomToSignals() {
  if (!map || signalMarkers.size === 0) return
  
  const bounds = []
  signalMarkers.forEach((marker) => {
    bounds.push(marker.getLatLng())
  })
  
  if (bounds.length > 0) {
    const mapBounds = L.latLngBounds(bounds)
    
    if (geometryLayer && geometryLayer.getBounds().isValid()) {
      mapBounds.extend(geometryLayer.getBounds())
    }
    
    if (mapBounds.isValid()) {
      map.fitBounds(mapBounds, { padding: [20, 20] })
    }
  }
}

// Expose rezoomToSignals so parent can call it
defineExpose({
  rezoomToSignals
})
</script>

<style scoped>
/* Remove focus outline from map and its elements */
:deep(.leaflet-container) {
  outline: none !important;
}

:deep(.leaflet-container:focus) {
  outline: none !important;
}

:deep(.leaflet-interactive) {
  outline: none !important;
}

:deep(.leaflet-interactive:focus) {
  outline: none !important;
}

:deep(path) {
  outline: none !important;
}

:deep(path:focus) {
  outline: none !important;
}
</style>