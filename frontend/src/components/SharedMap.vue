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
import { useThemeStore } from '@/stores/theme'
import { travelTimeColorScale, anomalyColorScale } from '@/utils/colorScale'
import { DEBUG_FRONTEND_LOGGING } from '@/config'

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
let markerStates = new Map() // Map signal ID to { category, isSelected, iconSize } for change detection
let xdLayers = new Map() // Map XD to layer
let markersLayer = null
let geometryLayer = null
let tileLayer = null // Reference to current tile layer for theme switching
let layerControl = null // Reference to layer control for base map switching
let previousDisplayedXDs = new Set() // Track previous filter state for selective updates

// SVG icon cache to avoid regenerating identical icons
let svgIconCache = new Map() // Map "category_isSelected_iconSize" to data URI

// Debouncing for rapid updates
let updateSelectionStylesScheduled = false

const geometryStore = useGeometryStore()
const mapStateStore = useMapStateStore()
const selectionStore = useSelectionStore()
const themeStore = useThemeStore()
const { featureCollection } = storeToRefs(geometryStore)
const { selectedSignalsList, selectedXdSegmentsList } = storeToRefs(selectionStore)

// Fixed marker size (no dynamic scaling on zoom)
const MARKER_ICON_SIZE = 30 // Fixed size in pixels (width/height)

// Get marker icon size (fixed, not zoom-dependent)
function getMarkerSize() {
  return MARKER_ICON_SIZE
}

// Categorize values into green/yellow/red thresholds
function getCategoryFromValue(value, dataType) {
  if (dataType === 'anomaly') {
    // Anomaly percentage thresholds
    if (value < 3.3) return 'green'
    if (value < 6.7) return 'yellow'
    return 'red'
  } else {
    // Travel Time Index thresholds
    if (value < 1.5) return 'green'
    if (value < 2.25) return 'yellow'
    return 'red'
  }
}

// Generate SVG traffic signal icon as data URI (with caching)
function createTrafficSignalIcon(category, isSelected, iconSize) {
  // Check cache first
  const cacheKey = `${category}_${isSelected}_${iconSize}_${themeStore.currentTheme}`
  const cached = svgIconCache.get(cacheKey)
  if (cached) {
    return cached
  }

  const isDark = themeStore.currentTheme === 'dark'
  const selectionColor = isDark ? '#FFFFFF' : '#000000'

  // Traffic light colors
  const activeColors = {
    green: '#4caf50',
    yellow: '#ffc107',
    red: '#d32f2f'
  }

  const inactiveColor = '#2a2a2a'
  const backplateColor = '#ffc107' // Yellow backplate (reflectorized)

  // Calculate sizes
  const width = iconSize
  const height = iconSize * 1.4 // Taller to fit 3 lights
  const lightRadius = iconSize * 0.12
  const backplateStroke = iconSize * 0.08
  const selectionStroke = isSelected ? iconSize * 0.15 : 0

  // Light positions (centered horizontally, stacked vertically)
  const centerX = width / 2
  const topY = height * 0.25
  const middleY = height * 0.5
  const bottomY = height * 0.75

  // Determine which light is active
  const redActive = category === 'red'
  const yellowActive = category === 'yellow'
  const greenActive = category === 'green'

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
      ${isSelected ? `
        <!-- Selection border -->
        <rect x="${selectionStroke/2}" y="${selectionStroke/2}"
              width="${width - selectionStroke}" height="${height - selectionStroke}"
              rx="${iconSize * 0.15}"
              fill="none" stroke="${selectionColor}" stroke-width="${selectionStroke}"/>
      ` : ''}

      <!-- Backplate (yellow outline) -->
      <rect x="${iconSize * 0.15}" y="${iconSize * 0.1}"
            width="${width - iconSize * 0.3}" height="${height - iconSize * 0.2}"
            rx="${iconSize * 0.1}"
            fill="#1a1a1a" stroke="${backplateColor}" stroke-width="${backplateStroke}"/>

      <!-- Red light (top) -->
      <circle cx="${centerX}" cy="${topY}" r="${lightRadius}"
              fill="${redActive ? activeColors.red : inactiveColor}"
              ${redActive ? `filter="url(#glow)"` : ''}/>

      <!-- Yellow light (middle) -->
      <circle cx="${centerX}" cy="${middleY}" r="${lightRadius}"
              fill="${yellowActive ? activeColors.yellow : inactiveColor}"
              ${yellowActive ? `filter="url(#glow)"` : ''}/>

      <!-- Green light (bottom) -->
      <circle cx="${centerX}" cy="${bottomY}" r="${lightRadius}"
              fill="${greenActive ? activeColors.green : inactiveColor}"
              ${greenActive ? `filter="url(#glow)"` : ''}/>

      <!-- Glow effect definition -->
      <defs>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="${lightRadius * 0.3}" result="coloredBlur"/>
          <feMerge>
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>
    </svg>
  `.trim()

  const dataUri = `data:image/svg+xml;base64,${btoa(svg)}`

  // Cache the result
  svgIconCache.set(cacheKey, dataUri)

  return dataUri
}

onMounted(() => {
  const mountStart = performance.now()
  console.log('🗺️ SharedMap: onMounted START')

  const t0 = performance.now()
  initializeMap()
  const t1 = performance.now()
  console.log(`🗺️ SharedMap: initializeMap took ${(t1 - t0).toFixed(2)}ms`)

  updateMarkers()
  const t2 = performance.now()
  console.log(`🗺️ SharedMap: updateMarkers took ${(t2 - t1).toFixed(2)}ms`)

  updateGeometry()
  const t3 = performance.now()
  console.log(`🗺️ SharedMap: updateGeometry took ${(t3 - t2).toFixed(2)}ms`)

  // Defer geometry loading until after initial render completes
  // This prevents blocking the UI with a 16k feature load
  requestIdleCallback(() => {
    const geometryLoadStart = performance.now()
    console.log('🗺️ SharedMap: Starting deferred geometry load')

    let fetchComplete = 0
    let parseComplete = 0
    let storeComplete = 0

    geometryStore.loadGeometry().then(() => {
      const geometryLoadEnd = performance.now()
      const totalTime = geometryLoadEnd - geometryLoadStart

      console.log(`🗺️ SharedMap: Geometry load COMPLETE in ${totalTime.toFixed(2)}ms`)
      console.log(`  Breakdown:`)
      console.log(`  - Network fetch + Arrow deser: see ApiService logs`)
      console.log(`  - Store assignment: ${(geometryLoadEnd - geometryLoadStart).toFixed(2)}ms total`)
    }).catch(error => {
      console.error('Failed to preload XD geometry:', error)
    })
  }, { timeout: 2000 })

  // Update mappings when signals load
  if (props.signals.length > 0) {
    const t4 = performance.now()
    selectionStore.updateMappings(props.signals)
    const t5 = performance.now()
    console.log(`🗺️ SharedMap: updateMappings took ${(t5 - t4).toFixed(2)}ms`)

    // Zoom to fit initial data
    autoZoomToSignals()
    const t6 = performance.now()
    console.log(`🗺️ SharedMap: autoZoomToSignals took ${(t6 - t5).toFixed(2)}ms`)
  }

  const mountEnd = performance.now()
  console.log(`🗺️ SharedMap: onMounted COMPLETE, total ${(mountEnd - mountStart).toFixed(2)}ms`)
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
  markerStates.clear()
  svgIconCache.clear()
  xdLayers.clear()
})

// Track previous signal IDs to detect when signal set actually changes
let previousSignalIds = new Set()

// Watch for signal data changes
watch(() => props.signals, (newSignals, oldSignals) => {
  const watchStart = performance.now()
  console.log('🔄 WATCH: props.signals changed (watch triggered)', {
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

  // Check if signal IDs actually changed (not just data values)
  const currentSignalIds = new Set(newSignals.map(s => s.ID))
  const signalSetChanged = currentSignalIds.size !== previousSignalIds.size ||
    ![...currentSignalIds].every(id => previousSignalIds.has(id))

  updateMarkers()
  const t2 = performance.now()
  console.log(`⏱️ updateMarkers: ${(t2 - t1).toFixed(2)}ms`)

  // Defer geometry updates for large datasets to avoid blocking
  const shouldDeferGeometry = newSignals.length > 5000
  if (shouldDeferGeometry) {
    console.log('⏳ Deferring geometry update (large dataset)')
    requestIdleCallback(() => {
      updateGeometry()
    }, { timeout: 1000 })
  } else {
    updateGeometry() // Update geometry to reflect filtered state
  }

  const t3 = performance.now()
  console.log(`⏱️ updateGeometry: ${shouldDeferGeometry ? '0.00 (deferred)' : (t3 - t2).toFixed(2)}ms`)

  // Only auto-zoom if the signal set actually changed
  if (signalSetChanged) {
    console.log('🔍 Signal set changed - performing auto-zoom')
    autoZoomToSignals()
    previousSignalIds = currentSignalIds
  } else {
    console.log('🔍 Signal set unchanged - skipping auto-zoom (data-only update)')
  }

  const t4 = performance.now()
  console.log(`⏱️ autoZoomToSignals: ${signalSetChanged ? (t4 - t3).toFixed(2) : '0.00 (skipped)'}ms`)
  console.log(`⏱️ TOTAL map updates: ${(t4 - t0).toFixed(2)}ms`)
  console.log(`⏱️ Watch overhead (trigger to start): ${(t0 - watchStart).toFixed(2)}ms`)
}, { deep: true })

// Watch for anomaly type changes
watch(() => props.anomalyType, () => {
  updateMarkers()
})

// Watch for geometry changes
watch(featureCollection, () => {
  updateGeometry()
}, { deep: true })

// Watch for selection changes to update styling (with debouncing)
watch([selectedSignalsList, selectedXdSegmentsList], () => {
  // Debounce rapid selection changes using requestAnimationFrame
  if (!updateSelectionStylesScheduled) {
    updateSelectionStylesScheduled = true
    requestAnimationFrame(() => {
      updateSelectionStyles()
      updateSelectionStylesScheduled = false
    })
  }
}, { deep: true })

// Watch for theme changes to update map tiles and selection styles
watch(() => themeStore.currentTheme, () => {
  // Clear SVG cache since theme affects icon rendering
  svgIconCache.clear()
  // Clear marker states to force regeneration with new theme
  markerStates.clear()

  updateTileLayer()
  updateSelectionStyles()
})

function updateTileLayer() {
  if (!map) return

  // Remove existing layer control and tile layers
  if (layerControl) {
    map.removeControl(layerControl)
    layerControl = null
  }
  if (tileLayer) {
    map.removeLayer(tileLayer)
    tileLayer = null
  }

  // Add appropriate tile layers based on theme
  const isDark = themeStore.currentTheme === 'dark'

  let roadmapLayer, satelliteLayer

  if (isDark) {
    // Dark mode: Use dark map without labels as base
    roadmapLayer = L.layerGroup([
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png', {
        maxZoom: 19
      }),
      // Add labels with better contrast on top
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}.png', {
        maxZoom: 19,
        opacity: 1.0
      })
    ])
  } else {
    // Light mode: Use standard light theme
    roadmapLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png', {
      maxZoom: 19
    })
  }

  // Satellite layer with labels (works for both light and dark themes)
  satelliteLayer = L.layerGroup([
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19
    }),
    // Add labels on top of satellite imagery
    L.tileLayer(isDark
      ? 'https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}.png'
      : 'https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}.png', {
      maxZoom: 19,
      opacity: 0.8
    })
  ])

  // Add roadmap as default layer
  tileLayer = roadmapLayer
  roadmapLayer.addTo(map)

  // Create layer control
  const baseMaps = {
    "Roadmap": roadmapLayer,
    "Satellite": satelliteLayer
  }

  layerControl = L.control.layers(baseMaps, null, {
    position: 'topright',
    collapsed: false
  }).addTo(map)
}

function initializeMap() {
  // Use saved map state or defaults
  const savedCenter = mapStateStore.mapCenter
  const savedZoom = mapStateStore.mapZoom

  map = L.map(mapContainer.value, {
    // Remove focus outline on click
    keyboard: false,
    attributionControl: false,
    // Enable smooth zoom but disable marker zoom animation specifically
    zoomAnimation: true,
    fadeAnimation: true,
    markerZoomAnimation: false, // Keep this disabled - marker repositioning happens instantly
    // Use preferCanvas for better performance with many features
    preferCanvas: true
  }).setView(savedCenter, savedZoom)

  // Add tile layer based on current theme
  updateTileLayer()

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

  // Track zoom lifecycle
  let zoomStartTime = null

  map.on('zoomstart', () => {
    zoomStartTime = performance.now()
    console.log('🔍 ZOOM LIFECYCLE: zoomstart', {
      currentZoom: map.getZoom(),
      markerCount: signalMarkers.size
    })
  })

  map.on('zoom', () => {
    const elapsed = zoomStartTime ? (performance.now() - zoomStartTime).toFixed(2) : 'unknown'
    console.log(`🔍 ZOOM LIFECYCLE: zoom event (${elapsed}ms since start)`, {
      currentZoom: map.getZoom()
    })
  })

  // Update marker sizes when zoom changes
  map.on('zoomend', () => {
    const timeSinceStart = zoomStartTime ? (performance.now() - zoomStartTime).toFixed(2) : 'unknown'
    console.log(`🔍 ZOOM LIFECYCLE: zoomend fired (${timeSinceStart}ms since zoomstart)`, {
      newZoom: map.getZoom(),
      markerCount: signalMarkers.size
    })

    const zoomEndHandlerStart = performance.now()
    updateMarkerSizes()
    const zoomEndHandlerTime = performance.now() - zoomEndHandlerStart

    const totalTime = zoomStartTime ? (performance.now() - zoomStartTime).toFixed(2) : 'unknown'
    console.log(`🔍 ZOOM LIFECYCLE: Complete - handler: ${zoomEndHandlerTime.toFixed(2)}ms, total: ${totalTime}ms`)
  })

  updateGeometry()
}

function updateGeometry() {
  if (!map || !geometryLayer) return

  const updateStart = performance.now()
  console.log('🗺️ updateGeometry: START', {
    xdLayersBeforeClear: xdLayers.size
  })

  const collection = featureCollection.value
  if (!collection || !Array.isArray(collection.features) || collection.features.length === 0) {
    console.log('🗺️ updateGeometry: NO FEATURES')
    return
  }

  // Build set of XD values from currently displayed signals
  const displayedXDs = new Set(props.signals.map(signal => signal.XD))
  console.log('🗺️ updateGeometry:', {
    totalFeatures: collection.features.length,
    displayedXDsCount: displayedXDs.size,
    displayedXDs: Array.from(displayedXDs)
  })

  // Get current data values for coloring
  const xdDataMap = getXdDataMap()

  // OPTIMIZATION: Identify which XDs changed filter state
  const newlyVisible = new Set([...displayedXDs].filter(xd => !previousDisplayedXDs.has(xd)))
  const newlyHidden = new Set([...previousDisplayedXDs].filter(xd => !displayedXDs.has(xd)))
  const stillVisible = new Set([...displayedXDs].filter(xd => previousDisplayedXDs.has(xd)))

  console.log('🗺️ updateGeometry: state changes', {
    newlyVisible: newlyVisible.size,
    newlyHidden: newlyHidden.size,
    stillVisible: stillVisible.size,
    totalToUpdate: newlyVisible.size + newlyHidden.size + stillVisible.size
  })

  // Track which layers we've seen (for cleanup of removed features)
  const seenXDs = new Set()

  let createdCount = 0
  let updatedCount = 0
  let skippedCount = 0

  // Helper function to update a layer's style
  const updateLayerStyle = (xd, feature = null) => {
    const existingLayer = xdLayers.get(xd)
    const isInFilteredSet = displayedXDs.has(xd)
    const dataValue = xdDataMap.get(xd)
    const isSelected = selectionStore.isXdSegmentSelected(xd)

    let fillColor = '#cccccc'
    if (isInFilteredSet && dataValue !== undefined && dataValue !== null) {
      if (props.dataType === 'anomaly') {
        const countColumn = props.anomalyType === "Point Source" ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
        const count = dataValue[countColumn] || 0
        const totalRecords = dataValue.RECORD_COUNT || 0
        const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0
        fillColor = anomalyColorScale(percentage)
      } else {
        const tti = dataValue.TRAVEL_TIME_INDEX || 0
        fillColor = travelTimeColorScale(tti)
      }
    }

    const newStyle = {
      color: isSelected ? '#000000' : (isInFilteredSet ? fillColor : '#808080'),
      weight: isSelected ? 3 : 1,
      opacity: isSelected ? 1 : (isInFilteredSet ? 0.8 : 0.3),
      fillColor: isInFilteredSet ? fillColor : '#cccccc',
      fillOpacity: isInFilteredSet ? 0.6 : 0.2
    }

    if (!existingLayer) {
      // Create new layer
      if (!feature) return false

      const layer = L.geoJSON(feature, {
        style: newStyle,
        onEachFeature: (feature, layer) => {
          const tooltipContent = createXdTooltip(xd, dataValue)
          layer.bindTooltip(tooltipContent, {
            sticky: true,
            direction: 'top'
          })

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
      createdCount++
      return true
    }

    // Update existing layer - style only, skip tooltip for performance
    // Tooltips will be regenerated on first hover via mouseover event
    existingLayer.eachLayer((childLayer) => {
      if (childLayer.setStyle) {
        childLayer.setStyle(newStyle)
      }

      // OPTIMIZATION: Use lazy tooltip updates - only regenerate on hover
      // This saves significant time during bulk geometry updates
      if (!childLayer._tooltipUpdateBound) {
        childLayer._tooltipUpdateBound = true
        childLayer.on('mouseover', () => {
          const tooltipContent = createXdTooltip(xd, getXdDataMap().get(xd))
          if (childLayer.getTooltip()) {
            childLayer.setTooltipContent(tooltipContent)
          } else {
            childLayer.bindTooltip(tooltipContent, {
              sticky: true,
              direction: 'top'
            })
          }
        })
      }
    })

    updatedCount++
    return true
  }

  // Build a map of XD -> feature for quick lookup
  const featureMap = new Map()
  collection.features.forEach(feature => {
    if (feature.properties?.XD) {
      featureMap.set(feature.properties.XD, feature)
      seenXDs.add(feature.properties.XD)
    }
  })

  // OPTIMIZATION: Only process XDs that need updates
  const xdsToUpdate = new Set([...newlyVisible, ...newlyHidden, ...stillVisible])

  console.log('🗺️ updateGeometry: processing', {
    totalXDsToProcess: xdsToUpdate.size,
    totalFeaturesAvailable: featureMap.size
  })

  xdsToUpdate.forEach(xd => {
    const feature = featureMap.get(xd)
    updateLayerStyle(xd, feature)
  })

  // Handle layers that don't exist yet (shouldn't happen but safety check)
  collection.features.forEach(feature => {
    if (!feature.properties?.XD) return
    const xd = feature.properties.XD

    if (!xdLayers.has(xd) && !xdsToUpdate.has(xd)) {
      // This XD wasn't in our update set but needs a layer created
      updateLayerStyle(xd, feature)
    }
  })

  // Remove layers that are no longer in the feature collection
  const layersToRemove = []
  xdLayers.forEach((layer, xd) => {
    if (!seenXDs.has(xd)) {
      layersToRemove.push(xd)
    }
  })

  layersToRemove.forEach(xd => {
    const layer = xdLayers.get(xd)
    if (layer) {
      geometryLayer.removeLayer(layer)
      xdLayers.delete(xd)
    }
  })

  // Update previousDisplayedXDs for next comparison
  previousDisplayedXDs = new Set(displayedXDs)

  const updateEnd = performance.now()
  console.log(`🗺️ updateGeometry: DONE in ${(updateEnd - updateStart).toFixed(2)}ms`, {
    created: createdCount,
    updated: updatedCount,
    skipped: skippedCount,
    removed: layersToRemove.length,
    totalLayers: xdLayers.size
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
          TRAVEL_TIME_INDEX: 0,
          AVG_TRAVEL_TIME: 0,
          RECORD_COUNT: 0,
          count: 0
        })
      }

      const existing = xdMap.get(signal.XD)
      existing.ANOMALY_COUNT += (signal.ANOMALY_COUNT || 0)
      existing.POINT_SOURCE_COUNT += (signal.POINT_SOURCE_COUNT || 0)
      existing.TRAVEL_TIME_INDEX += (signal.TRAVEL_TIME_INDEX || 0)
      existing.AVG_TRAVEL_TIME += (signal.AVG_TRAVEL_TIME || signal.AVG_TRAVEL_TIME_SECONDS || 0)
      existing.RECORD_COUNT += (signal.RECORD_COUNT || 0)
      existing.count += 1

      // Average the AVG_TRAVEL_TIME and TRAVEL_TIME_INDEX
      existing.AVG_TRAVEL_TIME = existing.AVG_TRAVEL_TIME / existing.count
      existing.TRAVEL_TIME_INDEX = existing.TRAVEL_TIME_INDEX / existing.count
    }
  })
  
  return xdMap
}

function createXdTooltip(xd, dataValue) {
  if (!dataValue) {
    return `<div><strong>XD Segment:</strong> ${xd}<br><em>No data</em></div>`
  }

  if (props.dataType === 'anomaly') {
    const anomalyCount = dataValue.ANOMALY_COUNT || 0
    const pointSourceCount = dataValue.POINT_SOURCE_COUNT || 0
    const totalRecords = dataValue.RECORD_COUNT || 0
    const percentage = totalRecords > 0 ? (anomalyCount / totalRecords) * 100 : 0

    return `
      <div>
        <strong>XD Segment:</strong> ${xd}<br>
        <strong>Anomaly Percentage:</strong> ${percentage.toFixed(1)}%<br>
        <strong>Total Anomalies:</strong> ${anomalyCount}<br>
        <strong>Point Source:</strong> ${pointSourceCount}
      </div>
    `
  } else {
    const travelTimeIndex = dataValue.TRAVEL_TIME_INDEX || 0
    return `
      <div>
        <strong>XD Segment:</strong> ${xd}<br>
        <strong>Travel Time Index:</strong> ${travelTimeIndex.toFixed(2)}
      </div>
    `
  }
}

// Helper function to update a single marker icon only if state changed
function updateMarkerIcon(signalId, marker, category, isSelected, iconSize) {
  const currentState = markerStates.get(signalId)

  // Check if state actually changed
  if (currentState &&
      currentState.category === category &&
      currentState.isSelected === isSelected &&
      currentState.iconSize === iconSize) {
    return false // No change needed
  }

  // State changed or new marker - update icon
  const iconStart = performance.now()
  const iconUrl = createTrafficSignalIcon(category, isSelected, iconSize)
  const iconGenTime = performance.now() - iconStart

  const divIconStart = performance.now()
  const icon = L.divIcon({
    html: `<img src="${iconUrl}" style="width: ${iconSize}px; height: ${iconSize * 1.4}px;">`,
    className: 'traffic-signal-icon',
    iconSize: [iconSize, iconSize * 1.4],
    iconAnchor: [iconSize / 2, iconSize * 1.4 / 2]
  })
  const divIconTime = performance.now() - divIconStart

  const setIconStart = performance.now()
  marker.setIcon(icon)
  const setIconTime = performance.now() - setIconStart

  if (setIconTime > 10) {
    console.log(`⚠️ SLOW setIcon for signal ${signalId}: ${setIconTime.toFixed(2)}ms`, {
      iconGenTime: iconGenTime.toFixed(2) + 'ms',
      divIconTime: divIconTime.toFixed(2) + 'ms',
      setIconTime: setIconTime.toFixed(2) + 'ms'
    })
  }

  // Update tracked state
  markerStates.set(signalId, { category, isSelected, iconSize })

  return true // Icon was updated
}

function updateMarkerSizes() {
  const perfStart = performance.now()
  console.log('⚙️ updateMarkerSizes: START', {
    markerCount: signalMarkers.size,
    hasMap: !!map,
    hasMarkersLayer: !!markersLayer
  })

  if (!map || !markersLayer) return

  const iconSize = getMarkerSize()
  console.log(`⚙️ updateMarkerSizes: iconSize = ${iconSize}`)
  let updatedCount = 0
  let findSignalTime = 0
  let getCategoryTime = 0
  let updateIconTime = 0

  // BUILD LOOKUP MAP ONCE - O(n) instead of O(n²)
  const mapBuildStart = performance.now()
  const signalMap = new Map()
  props.signals.forEach(signal => {
    signalMap.set(signal.ID, signal)
  })
  const mapBuildTime = performance.now() - mapBuildStart
  console.log(`⚙️ Built signal lookup map in ${mapBuildTime.toFixed(2)}ms for ${props.signals.length} signals`)

  signalMarkers.forEach((marker, signalId) => {
    const loopStart = performance.now()
    const isSelected = selectionStore.isSignalSelected(signalId)

    // Get current marker data to determine category
    let category = 'green' // Default
    const findStart = performance.now()
    const signal = signalMap.get(signalId) // O(1) lookup instead of O(n) find
    findSignalTime += (performance.now() - findStart)

    const categoryStart = performance.now()
    if (signal) {
      if (props.dataType === 'anomaly') {
        const countColumn = props.anomalyType === "Point Source" ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
        const count = signal[countColumn] || 0
        const totalRecords = signal.RECORD_COUNT || 0
        const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0
        category = getCategoryFromValue(percentage, 'anomaly')
      } else {
        const tti = signal.TRAVEL_TIME_INDEX || 0
        category = getCategoryFromValue(tti, 'travel-time')
      }
    }
    getCategoryTime += (performance.now() - categoryStart)

    // Only update if state changed
    const iconStart = performance.now()
    if (updateMarkerIcon(signalId, marker, category, isSelected, iconSize)) {
      updatedCount++
    }
    updateIconTime += (performance.now() - iconStart)
  })

  const perfEnd = performance.now()
  console.log(`⚙️ updateMarkerSizes: COMPLETE in ${(perfEnd - perfStart).toFixed(2)}ms`, {
    totalMarkers: signalMarkers.size,
    updatedCount,
    breakdown: {
      findSignalTime: findSignalTime.toFixed(2) + 'ms',
      getCategoryTime: getCategoryTime.toFixed(2) + 'ms',
      updateIconTime: updateIconTime.toFixed(2) + 'ms'
    }
  })
}

function updateMarkers() {
  if (!map || !markersLayer) return

  if (props.signals.length === 0) {
    markersLayer.clearLayers()
    signalMarkers.clear()
    markerStates.clear() // Clean up state tracking
    return
  }

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
          POINT_SOURCE_COUNT: 0,
          RECORD_COUNT: 0
        })
      }

      const group = signalGroups.get(signal.ID)
      group.ANOMALY_COUNT += (signal.ANOMALY_COUNT || 0)
      group.POINT_SOURCE_COUNT += (signal.POINT_SOURCE_COUNT || 0)
      group.RECORD_COUNT += (signal.RECORD_COUNT || 0)
    })

    const aggregatedSignals = Array.from(signalGroups.values())
    const newSignalIds = new Set(aggregatedSignals.map(s => s.ID))

    // OPTIMIZATION: Update existing markers, only create/remove as needed
    const markersToRemove = []
    signalMarkers.forEach((marker, signalId) => {
      if (!newSignalIds.has(signalId)) {
        markersToRemove.push(signalId)
      }
    })

    // Remove markers that are no longer in the dataset
    markersToRemove.forEach(signalId => {
      const marker = signalMarkers.get(signalId)
      if (marker) {
        markersLayer.removeLayer(marker)
        signalMarkers.delete(signalId)
        markerStates.delete(signalId) // Clean up state tracking
      }
    })

    // Update existing markers or create new ones
    aggregatedSignals.forEach(signal => {
      bounds.push([signal.LATITUDE, signal.LONGITUDE])

      const count = signal[countColumn] || 0
      const totalRecords = signal.RECORD_COUNT || 0
      const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0

      const category = getCategoryFromValue(percentage, 'anomaly')
      const isSelected = selectionStore.isSignalSelected(signal.ID)

      const existingMarker = signalMarkers.get(signal.ID)

      if (existingMarker) {
        // Update existing marker icon only if state changed
        const iconSize = getMarkerSize()
        updateMarkerIcon(signal.ID, existingMarker, category, isSelected, iconSize)

        // Tooltip will be updated lazily on mouseover
      } else {
        // Create new marker with traffic signal icon
        const iconSize = getMarkerSize()
        const iconUrl = createTrafficSignalIcon(category, isSelected, iconSize)
        const icon = L.divIcon({
          html: `<img src="${iconUrl}" style="width: ${iconSize}px; height: ${iconSize * 1.4}px;">`,
          className: 'traffic-signal-icon',
          iconSize: [iconSize, iconSize * 1.4],
          iconAnchor: [iconSize / 2, iconSize * 1.4 / 2]
        })

        const marker = L.marker([signal.LATITUDE, signal.LONGITUDE], {
          icon: icon,
          interactive: true
        })

        const tooltipContent = `
          <div>
            <h4>Signal ${signal.ID}</h4>
            <p><strong>Anomaly Percentage:</strong> ${percentage.toFixed(1)}%</p>
            <p><strong>Total Anomalies:</strong> ${signal.ANOMALY_COUNT || 0}</p>
            <p><strong>Point Source:</strong> ${signal.POINT_SOURCE_COUNT || 0}</p>
            <p><strong>Approach:</strong> ${signal.APPROACH ? 'Yes' : 'No'}</p>
          </div>
        `

        marker.bindTooltip(tooltipContent, {
          direction: 'top',
          offset: [0, -10]
        })

        // Lazy tooltip update on mouseover
        marker.on('mouseover', () => {
          const currentSignal = props.signals.find(s => s.ID === signal.ID)
          if (currentSignal) {
            const currentCount = currentSignal[countColumn] || 0
            const currentTotal = currentSignal.RECORD_COUNT || 0
            const currentPercentage = currentTotal > 0 ? (currentCount / currentTotal) * 100 : 0

            const updatedTooltip = `
              <div>
                <h4>Signal ${currentSignal.ID}</h4>
                <p><strong>Anomaly Percentage:</strong> ${currentPercentage.toFixed(1)}%</p>
                <p><strong>Total Anomalies:</strong> ${currentSignal.ANOMALY_COUNT || 0}</p>
                <p><strong>Point Source:</strong> ${currentSignal.POINT_SOURCE_COUNT || 0}</p>
                <p><strong>Approach:</strong> ${currentSignal.APPROACH ? 'Yes' : 'No'}</p>
              </div>
            `
            marker.setTooltipContent(updatedTooltip)
          }
        })

        marker.on('click', (e) => {
          L.DomEvent.stopPropagation(e)
          selectionStore.toggleSignal(signal.ID)
          emit('selection-changed')
        })

        markersLayer.addLayer(marker)
        signalMarkers.set(signal.ID, marker)
      }
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
          TRAVEL_TIME_INDEX: 0,
          RECORD_COUNT: 0,
          totalForAvg: 0,
          countForAvg: 0,
          ttiCount: 0
        })
      }

      const group = signalGroups.get(signal.ID)
      const tti = Number(signal.TRAVEL_TIME_INDEX ?? 0) || 0
      const records = Number(signal.RECORD_COUNT ?? 0) || 0
      const avgTime = Number(signal.AVG_TRAVEL_TIME ?? signal.AVG_TRAVEL_TIME_SECONDS ?? 0) || 0

      group.TRAVEL_TIME_INDEX += tti
      group.ttiCount += 1
      group.RECORD_COUNT += records

      // For weighted average calculation
      if (records > 0 && avgTime > 0) {
        group.totalForAvg += avgTime * records
        group.countForAvg += records
      }
    })
    
    const aggregatedSignals = Array.from(signalGroups.values())
    const newSignalIds = new Set(aggregatedSignals.map(s => s.ID))

    // OPTIMIZATION: Update existing markers, only create/remove as needed
    const markersToRemove = []
    signalMarkers.forEach((marker, signalId) => {
      if (!newSignalIds.has(signalId)) {
        markersToRemove.push(signalId)
      }
    })

    // Remove markers that are no longer in the dataset
    markersToRemove.forEach(signalId => {
      const marker = signalMarkers.get(signalId)
      if (marker) {
        markersLayer.removeLayer(marker)
        signalMarkers.delete(signalId)
        markerStates.delete(signalId) // Clean up state tracking
      }
    })

    // Update existing markers or create new ones
    aggregatedSignals.forEach(signal => {
      bounds.push([signal.LATITUDE, signal.LONGITUDE])

      // Calculate average TTI for coloring
      const avgTTI = signal.ttiCount > 0
        ? signal.TRAVEL_TIME_INDEX / signal.ttiCount
        : 0

      const category = getCategoryFromValue(avgTTI, 'travel-time')
      const isSelected = selectionStore.isSignalSelected(signal.ID)

      const existingMarker = signalMarkers.get(signal.ID)

      if (existingMarker) {
        // Update existing marker icon only if state changed
        const iconSize = getMarkerSize()
        updateMarkerIcon(signal.ID, existingMarker, category, isSelected, iconSize)

        // Tooltip will be updated lazily on mouseover
      } else {
        // Create new marker with traffic signal icon
        const iconSize = getMarkerSize()
        const iconUrl = createTrafficSignalIcon(category, isSelected, iconSize)
        const icon = L.divIcon({
          html: `<img src="${iconUrl}" style="width: ${iconSize}px; height: ${iconSize * 1.4}px;">`,
          className: 'traffic-signal-icon',
          iconSize: [iconSize, iconSize * 1.4],
          iconAnchor: [iconSize / 2, iconSize * 1.4 / 2]
        })

        const marker = L.marker([signal.LATITUDE, signal.LONGITUDE], {
          icon: icon,
          interactive: true
        })

        const ttiDisplay = Number.isFinite(avgTTI) ? avgTTI.toFixed(2) : 'N/A'

        const tooltipContent = `
          <div>
            <h4>Signal ${signal.ID}</h4>
            <p><strong>Travel Time Index:</strong> ${ttiDisplay}</p>
            <p><strong>Approach:</strong> ${signal.APPROACH ? 'Yes' : 'No'}</p>
          </div>
        `

        marker.bindTooltip(tooltipContent, {
          direction: 'top',
          offset: [0, -10]
        })

        // Lazy tooltip update on mouseover
        marker.on('mouseover', () => {
          // Recalculate aggregated TTI from current signal data
          const currentGroup = {
            TRAVEL_TIME_INDEX: 0,
            ttiCount: 0,
            APPROACH: signal.APPROACH
          }

          props.signals.forEach(s => {
            if (s.ID === signal.ID) {
              const tti = Number(s.TRAVEL_TIME_INDEX ?? 0) || 0
              currentGroup.TRAVEL_TIME_INDEX += tti
              currentGroup.ttiCount += 1
            }
          })

          const currentAvgTTI = currentGroup.ttiCount > 0
            ? currentGroup.TRAVEL_TIME_INDEX / currentGroup.ttiCount
            : 0
          const currentTtiDisplay = Number.isFinite(currentAvgTTI) ? currentAvgTTI.toFixed(2) : 'N/A'

          const updatedTooltip = `
            <div>
              <h4>Signal ${signal.ID}</h4>
              <p><strong>Travel Time Index:</strong> ${currentTtiDisplay}</p>
              <p><strong>Approach:</strong> ${currentGroup.APPROACH ? 'Yes' : 'No'}</p>
            </div>
          `
          marker.setTooltipContent(updatedTooltip)
        })

        marker.on('click', (e) => {
          L.DomEvent.stopPropagation(e)
          selectionStore.toggleSignal(signal.ID)
          emit('selection-changed')
        })

        markersLayer.addLayer(marker)
        signalMarkers.set(signal.ID, marker)
      }
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

    // OPTIMIZATION: Skip XD bounds iteration for large datasets (>20 signals)
    // Marker bounds are sufficient for zoom, and iterating XDs is expensive
    const displayedXDs = new Set(props.signals.map(signal => signal.XD))
    let xdBoundsAdded = 0

    if (signalMarkers.size <= 20) {
      // Small dataset - include XD bounds for precision
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
    } else {
      // Large dataset - skip XD iteration, use marker bounds only
      console.log('🔍 autoZoomToSignals: SKIPPING XD bounds (>20 signals, using marker bounds only)')
    }

    if (mapBounds.isValid()) {
      console.log('🔍 autoZoomToSignals: CALLING fitBounds')

      // OPTIMIZATION: For very large datasets, use faster fitBounds options
      if (signalMarkers.size > 100) {
        // Large dataset - use animate: false for instant zoom, no animation overhead
        map.fitBounds(mapBounds, {
          padding: [50, 50],
          maxZoom: 15,
          animate: false,  // Skip animation for faster performance
          duration: 0       // No transition time
        })
      } else {
        // Small dataset - use animated zoom for better UX
        map.fitBounds(mapBounds, { padding: [50, 50], maxZoom: 15 })
      }

      console.log('🔍 autoZoomToSignals: DONE, new zoom:', map.getZoom())
    } else {
      console.log('🔍 autoZoomToSignals: SKIPPED (invalid bounds)')
    }
  }
}

function updateSelectionStyles() {
  // Update signal marker icons with selection state
  const iconSize = getMarkerSize()
  let updatedCount = 0

  signalMarkers.forEach((marker, signalId) => {
    const isSelected = selectionStore.isSignalSelected(signalId)

    // Get current marker data to determine category
    let category = 'green' // Default
    const signal = props.signals.find(s => s.ID === signalId)

    if (signal) {
      if (props.dataType === 'anomaly') {
        const countColumn = props.anomalyType === "Point Source" ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
        const count = signal[countColumn] || 0
        const totalRecords = signal.RECORD_COUNT || 0
        const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0
        category = getCategoryFromValue(percentage, 'anomaly')
      } else {
        const tti = signal.TRAVEL_TIME_INDEX || 0
        category = getCategoryFromValue(tti, 'travel-time')
      }
    }

    // Only update if state changed
    if (updateMarkerIcon(signalId, marker, category, isSelected, iconSize)) {
      updatedCount++
    }
  })

  if (DEBUG_FRONTEND_LOGGING && updatedCount > 0) {
    console.log(`🔄 updateSelectionStyles: Updated ${updatedCount}/${signalMarkers.size} markers`)
  }

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
        const totalRecords = dataValue.RECORD_COUNT || 0
        const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0
        fillColor = anomalyColorScale(percentage)
      } else {
        const tti = dataValue.TRAVEL_TIME_INDEX || 0
        fillColor = travelTimeColorScale(tti)
      }
    }

    const styleUpdate = {
      color: isSelected ? selectionColor : (isInFilteredSet ? fillColor : '#808080'),
      weight: isSelected ? 3 : 1,
      opacity: isSelected ? 1 : (isInFilteredSet ? 0.8 : 0.3),
      fillColor: isInFilteredSet ? fillColor : '#cccccc',  // FIX: Consistent with color logic
      fillOpacity: isInFilteredSet ? (isSelected ? 0.7 : 0.6) : 0.2
    }

    // GeoJSON layers are LayerGroups, need to iterate through all child layers
    layer.eachLayer((childLayer) => {
      if (childLayer.setStyle) {
        childLayer.setStyle(styleUpdate)
      }
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

/* Custom traffic signal icon styling */
:deep(.traffic-signal-icon) {
  background: none !important;
  border: none !important;
  margin: 0 !important;
  padding: 0 !important;
  /* Center the icon on the point */
  margin-left: -15px !important; /* Half of MARKER_ICON_SIZE (30px / 2) */
  margin-top: -21px !important; /* Half of icon height (30px * 1.4 / 2) */
}

:deep(.traffic-signal-icon img) {
  display: block;
  pointer-events: none;
}
</style>