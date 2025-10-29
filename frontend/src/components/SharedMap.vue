<template>
  <div ref="mapContainer" style="height: 100%; width: 100%;"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, onActivated, watch, computed } from 'vue'
import { storeToRefs } from 'pinia'
import L from 'leaflet'
import 'leaflet-draw'
import 'leaflet-draw/dist/leaflet.draw.css'
import { useGeometryStore } from '@/stores/geometry'
import { useMapStateStore } from '@/stores/mapState'
import { useSelectionStore } from '@/stores/selection'
import { useThemeStore } from '@/stores/theme'
import {
  travelTimeColorScale,
  anomalyColorScale,
  beforeAfterDifferenceColorScale,
  changepointColorScale
} from '@/utils/colorScale'
import { DEBUG_FRONTEND_LOGGING } from '@/config'

const props = defineProps({
  signals: {
    type: Array,
    default: () => []
  },
  xdSegments: {
    type: Array,
    default: () => []
  },
  dataType: {
    type: String,
    default: 'travel-time', // 'travel-time', 'anomaly', 'before-after', or 'changepoints'
    validator: (value) => ['travel-time', 'anomaly', 'before-after', 'changepoints'].includes(value)
  },
  anomalyType: {
    type: String,
    default: 'All'
  },
  autoZoomEnabled: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['selection-changed'])

const mapContainer = ref(null)
let map = null
let signalMarkers = new Map() // Map signal ID to marker
let markerStates = new Map() // Map signal ID to { category, isSelected, iconSize, dataHash, useSvg, customColor, zIndexCategory } for change detection
let xdLayers = new Map() // Map XD to layer
let markersLayer = null
let geometryLayer = null
let tileLayer = null // Reference to current tile layer for theme switching
let layerControl = null // Reference to layer control for base map switching
let previousDisplayedXDs = new Set() // Track previous filter state for selective updates
let drawControl = null // Reference to draw control
let drawnItems = null // Layer group for drawn items

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

// Signal count threshold for switching between circle and SVG icons
const SIGNAL_COUNT_THRESHOLD = 200 // Switch to SVG icons when 200 or fewer signals are visible

// Marker sizes based on severity (for circles - larger = more important)
const MARKER_SIZES = {
  green: 20,   // Smaller, less important
  yellow: 28,  // Medium
  red: 36      // Largest, most important
}

// SVG icon base size (used when zoomed in)
const SVG_ICON_SIZE = 30

// Changepoint marker sizing bounds (in pixels)
const CHANGEPOINT_ICON_SIZE_RANGE = {
  min: 18,
  max: 44
}

function getChangepointCategory(avgPctChange) {
  if (!Number.isFinite(avgPctChange)) {
    return 'yellow'
  }
  // avgPctChange is stored as decimal (0.05 = 5%), so multiply by 100 for thresholds
  const pctAsWholeNumber = avgPctChange * 100
  if (pctAsWholeNumber <= -5) {
    return 'green'
  }
  if (pctAsWholeNumber >= 5) {
    return 'red'
  }
  return 'yellow'
}

function computeChangepointIconSize(absPctSum, minAbs, maxAbs) {
  const value = Number.isFinite(absPctSum) ? Math.abs(absPctSum) : 0
  const min = CHANGEPOINT_ICON_SIZE_RANGE.min
  const max = CHANGEPOINT_ICON_SIZE_RANGE.max

  if (!Number.isFinite(minAbs) || minAbs === Infinity) {
    minAbs = 0
  }
  if (!Number.isFinite(maxAbs) || maxAbs === -Infinity || maxAbs <= 0) {
    return (min + max) / 2
  }
  if (maxAbs === minAbs) {
    return Math.min(max, Math.max(min, min + (max - min) * 0.5))
  }

  const normalized = (value - minAbs) / (maxAbs - minAbs)
  const clamped = Math.min(1, Math.max(0, normalized))
  const size = min + clamped * (max - min)
  return Math.min(max, Math.max(min, size))
}

function buildChangepointVisualMap(signals) {
  let minAbs = Infinity
  let maxAbs = -Infinity

  const processed = signals
    .map(signal => {
      if (!signal || signal.ID === undefined || signal.ID === null) {
        return null
      }
      const absSumRaw = Number(signal.ABS_PCT_SUM ?? 0)
      const absSum = Number.isFinite(absSumRaw) ? Math.abs(absSumRaw) : 0
      const avgPctRaw = Number(signal.AVG_PCT_CHANGE ?? 0)
      const avgPct = Number.isFinite(avgPctRaw) ? avgPctRaw : 0

      minAbs = Math.min(minAbs, absSum)
      maxAbs = Math.max(maxAbs, absSum)

      return { signal, absSum, avgPct }
    })
    .filter(Boolean)

  if (minAbs === Infinity) minAbs = 0
  if (maxAbs === -Infinity) maxAbs = 0

  const visualMap = new Map()

  processed.forEach(({ signal, absSum, avgPct }) => {
    const category = getChangepointCategory(avgPct)
    // avgPct is stored as decimal (0.05 = 5%), multiply by 100 for color scale
    const color = changepointColorScale(avgPct * 100)
    const iconSize = computeChangepointIconSize(absSum, minAbs, maxAbs)
    const dataHashParts = [
      absSum.toFixed(4),
      avgPct.toFixed(4),
      Number(signal.CHANGEPOINT_COUNT ?? 0).toFixed(0),
      Number(signal.TOP_PCT_CHANGE ?? 0).toFixed(4),
      Number(signal.TOP_AVG_DIFF ?? 0).toFixed(4)
    ]

    visualMap.set(signal.ID, {
      signal,
      absSum,
      avgPct,
      category,
      color,
      iconSize,
      dataHash: dataHashParts.join('|')
    })
  })

  return { visualMap, minAbs, maxAbs }
}

function buildChangepointSignalTooltip(visual) {
  if (!visual) {
    return '<div><em>No changepoint data</em></div>'
  }

  const { signal } = visual
  const signalName = signal.NAME || `Signal ${signal.ID}`
  const count = Number(signal.CHANGEPOINT_COUNT ?? 0)
  const topTimestamp = signal.TOP_TIMESTAMP ? new Date(signal.TOP_TIMESTAMP).toLocaleString() : 'N/A'
  const topRoad = signal.TOP_ROADNAME || 'Unknown road'
  const topBearing = signal.TOP_BEARING || 'N/A'
  const topPctChangeRaw = Number(signal.TOP_PCT_CHANGE ?? 0)
  const topAvgDiffRaw = Number(signal.TOP_AVG_DIFF ?? 0)
  const topPctDisplay = Number.isFinite(topPctChangeRaw) ? `${(topPctChangeRaw * 100).toFixed(1)}%` : 'N/A'
  const topAvgDiffDisplay = Number.isFinite(topAvgDiffRaw) ? `${topAvgDiffRaw.toFixed(1)} s` : 'N/A'

  return `
    <div>
      <h4>${signalName}</h4>
      <p><strong>Changepoints:</strong> ${count}</p>
      <hr />
      <p><strong>Top Changepoint:</strong></p>
      <p>${topRoad} &middot; Bearing ${topBearing}</p>
      <p><strong>Percent Change:</strong> ${topPctDisplay}</p>
      <p><strong>Avg Diff:</strong> ${topAvgDiffDisplay}</p>
      <p><strong>Timestamp:</strong> ${topTimestamp}</p>
    </div>
  `
}

// Get marker icon size based on category and icon type
function getMarkerSize(category, useSvg = false) {
  if (useSvg) {
    return SVG_ICON_SIZE // Fixed size for SVG traffic signals
  }
  return MARKER_SIZES[category] || MARKER_SIZES.green
}

// Get z-index offset based on category (higher severity = higher z-index)
function getZIndexOffset(category) {
  const zIndexOffsets = {
    green: 0,
    yellow: 100,
    red: 200
  }
  return zIndexOffsets[category] || 0
}

// Get traffic light colors based on colorblind mode
function getTrafficLightColors() {
  if (themeStore.colorblindMode) {
    // Colorblind-friendly colors (based on Wong 2011 / IBM Design)
    return {
      green: '#0072B2',    // Blue (replaces green)
      yellow: '#F0E442',   // Yellow
      red: '#D55E00'       // Vermillion (replaces red)
    }
  } else {
    // Standard colors
    return {
      green: '#4caf50',
      yellow: '#ffc107',
      red: '#d32f2f'
    }
  }
}

// Check if we should use SVG icons based on number of signals visible in current viewport
// signalData parameter is optional - used during updateMarkers to get accurate count during transition
function shouldUseSvgIcons(signalData = null) {
  if (!map) {
    console.log('🎨 shouldUseSvgIcons: no map yet, defaulting to circles')
    return false
  }

  // Count how many signals are currently visible in the map viewport
  const bounds = map.getBounds()
  let visibleCount = 0

  if (signalData && Array.isArray(signalData)) {
    // Use provided signal data (during updateMarkers when signalMarkers may be stale)
    signalData.forEach(signal => {
      if (signal.LATITUDE && signal.LONGITUDE && bounds.contains([signal.LATITUDE, signal.LONGITUDE])) {
        visibleCount++
      }
    })
  } else {
    // Use existing markers (for other cases like zoom events)
    signalMarkers.forEach((marker, signalId) => {
      const latLng = marker.getLatLng()
      if (bounds.contains(latLng)) {
        visibleCount++
      }
    })
  }

  const useSvg = visibleCount <= SIGNAL_COUNT_THRESHOLD
  return useSvg
}

// Categorize values into green/yellow/red thresholds
function getCategoryFromValue(value, dataType) {
  if (dataType === 'anomaly') {
    // Anomaly percentage thresholds: 0, 5, 10
    if (value < 5) return 'green'
    if (value < 10) return 'yellow'
    return 'red'
  } else if (dataType === 'changepoints') {
    if (value <= -5) return 'green'
    if (value >= 5) return 'red'
    return 'yellow'
  } else {
    // Travel Time Index thresholds: 1, 2, 3
    if (value < 2) return 'green'
    if (value < 3) return 'yellow'
    return 'red'
  }
}

// Generate SVG circle icon as data URI (with caching) - used when zoomed out
function createCircleIcon(category, isSelected, iconSize, customColor = null) {
  // Check cache first (include custom colors in cache key)
  const cacheKey = customColor
    ? `circle_custom_${customColor}_${isSelected}_${iconSize}_${themeStore.currentTheme}`
    : `circle_${category}_${isSelected}_${iconSize}_${themeStore.currentTheme}`
  const cached = svgIconCache.get(cacheKey)
  if (cached) {
    return cached
  }

  const isDark = themeStore.currentTheme === 'dark'
  const selectionColor = isDark ? '#FFFFFF' : '#000000'

  let fillColor
  let opacity

  if (customColor) {
    fillColor = customColor
    opacity = 0.9
  } else {
    // Circle colors matching the traffic light colors (colorblind-safe if enabled)
    const fillColors = getTrafficLightColors()

    // Opacity based on severity - less important signals are more transparent
    const opacities = {
      green: 0.5,   // Semi-transparent (fade into background)
      yellow: 0.8,  // More visible
      red: 1.0      // Fully opaque (most important)
    }

    fillColor = fillColors[category] || fillColors.green
    opacity = opacities[category] || opacities.green
  }

  const radius = iconSize / 2
  const selectionStrokeWidth = isSelected ? iconSize * 0.12 : 0

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${iconSize}" height="${iconSize}" viewBox="0 0 ${iconSize} ${iconSize}">
      ${isSelected ? `
        <!-- Selection border -->
        <circle cx="${radius}" cy="${radius}" r="${radius - selectionStrokeWidth/2}"
                fill="none" stroke="${selectionColor}" stroke-width="${selectionStrokeWidth}"/>
      ` : ''}

      <!-- Main circle -->
      <circle cx="${radius}" cy="${radius}" r="${radius - (isSelected ? selectionStrokeWidth : iconSize * 0.08)}"
              fill="${fillColor}" opacity="${opacity}"/>
    </svg>
  `.trim()

  const dataUri = `data:image/svg+xml;base64,${btoa(svg)}`

  // Cache the result
  svgIconCache.set(cacheKey, dataUri)

  return dataUri
}

// Generate SVG traffic signal icon as data URI (with caching) - used when zoomed in
function createTrafficSignalIcon(category, isSelected, iconSize) {
  // Check cache first
  const cacheKey = `signal_${category}_${isSelected}_${iconSize}_${themeStore.currentTheme}`
  const cached = svgIconCache.get(cacheKey)
  if (cached) {
    return cached
  }

  const isDark = themeStore.currentTheme === 'dark'
  const selectionColor = isDark ? '#FFFFFF' : '#000000'

  // Traffic light colors (colorblind-safe if enabled)
  const activeColors = getTrafficLightColors()

  const inactiveColor = '#2a2a2a'
  const backplateColor = activeColors.yellow // Yellow backplate (reflectorized)

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
    selectionStore.updateMappings(props.signals, props.xdSegments)
    const t5 = performance.now()
    console.log(`🗺️ SharedMap: updateMappings took ${(t5 - t4).toFixed(2)}ms`)

    // Only auto-zoom on first load if there's no saved map state from another page
    // Check if we have a non-default saved state (default is zoom 4 at center of US)
    const hasUserDefinedMapState = mapStateStore.mapZoom !== 4 ||
                                    Math.abs(mapStateStore.mapCenter[0] - 39.0) > 0.01 ||
                                    Math.abs(mapStateStore.mapCenter[1] - (-98.0)) > 0.01

    if (!hasUserDefinedMapState) {
      console.log('🔍 No saved map state - performing initial auto-zoom')
      autoZoomToSignals()
      const t6 = performance.now()
      console.log(`🗺️ SharedMap: autoZoomToSignals took ${(t6 - t5).toFixed(2)}ms`)
    } else {
      console.log('🔍 Saved map state exists - skipping initial auto-zoom')
    }

    // Initialize previousSignalIds to prevent auto-zoom on first data update
    previousSignalIds = new Set(props.signals.map(s => s.ID))
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

onActivated(() => {
  console.log('🗺️ SharedMap: onActivated - restoring shared map state')

  if (map && mapStateStore.mapCenter && mapStateStore.mapZoom) {
    const savedCenter = mapStateStore.mapCenter
    const savedZoom = mapStateStore.mapZoom

    // Get current map state
    const currentCenter = map.getCenter()
    const currentZoom = map.getZoom()

    // Check if map state differs from saved state
    const centerChanged = Math.abs(currentCenter.lat - savedCenter[0]) > 0.0001 ||
                         Math.abs(currentCenter.lng - savedCenter[1]) > 0.0001
    const zoomChanged = currentZoom !== savedZoom

    if (centerChanged || zoomChanged) {
      console.log('🗺️ SharedMap: Restoring saved map state', {
        from: { center: [currentCenter.lat, currentCenter.lng], zoom: currentZoom },
        to: { center: savedCenter, zoom: savedZoom }
      })
      // Restore saved map state from store
      map.setView(savedCenter, savedZoom, { animate: false })
    } else {
      console.log('🗺️ SharedMap: Map state already matches saved state')
    }
  }
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
    selectionStore.updateMappings(newSignals, props.xdSegments)
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
  let autoZoomExecuted = false
  if (signalSetChanged) {
    previousSignalIds = currentSignalIds

    if (props.autoZoomEnabled) {
      console.log('🔍 Signal set changed - performing auto-zoom')
      autoZoomToSignals()
      autoZoomExecuted = true
    } else {
      console.log('🔍 Signal set changed - auto-zoom suppressed (autoZoomEnabled=false)')
    }
  } else {
    console.log('🔍 Signal set unchanged - skipping auto-zoom (data-only update)')
  }

  const t4 = performance.now()
  console.log(`⏱️ autoZoomToSignals: ${autoZoomExecuted ? (t4 - t3).toFixed(2) : '0.00 (skipped)'}ms`)
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

// Watch for colorblind mode changes to update marker and geometry colors
watch(() => themeStore.colorblindMode, () => {
  // Clear SVG cache since colorblind mode affects icon colors
  svgIconCache.clear()
  // Clear marker states to force regeneration with new colors
  markerStates.clear()

  // Update markers and geometry with new color scheme
  updateMarkerSizes()
  updateGeometry()
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

  // Initialize drawing controls for lasso selection
  drawnItems = L.featureGroup().addTo(map)

  drawControl = new L.Control.Draw({
    draw: {
      polygon: {
        allowIntersection: false,
        drawError: {
          color: '#e1e100',
          message: '<strong>Error:</strong> Shape edges cannot cross!'
        },
        shapeOptions: {
          color: '#97009c',
          weight: 2,
          opacity: 0.8,
          fillOpacity: 0.1
        }
      },
      polyline: false,
      rectangle: false,
      circle: false,
      marker: false,
      circlemarker: false
    },
    edit: false // Disable edit mode completely for simplicity
  })

  map.addControl(drawControl)

  // Handle polygon creation
  map.on(L.Draw.Event.CREATED, (event) => {
    const layer = event.layer

    // Clear any existing polygon (only allow one at a time)
    drawnItems.clearLayers()

    // Temporarily add the polygon to get its geometry
    drawnItems.addLayer(layer)

    // Get the polygon bounds and select XD segments
    const polygon = layer.toGeoJSON()
    selectXdSegmentsInPolygon(polygon)

    // Hide the polygon immediately after selection is made
    drawnItems.clearLayers()
  })

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
    const currentZoom = map.getZoom()
    const usingSvgIcons = shouldUseSvgIcons()

    console.log(`🔍 ZOOM LIFECYCLE: zoomend fired (${timeSinceStart}ms since zoomstart)`, {
      newZoom: currentZoom,
      markerCount: signalMarkers.size,
      iconType: usingSvgIcons ? 'SVG traffic signals' : 'circles',
      signalCountThreshold: SIGNAL_COUNT_THRESHOLD
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

  // Build set of XD values from currently displayed XD segments
  // Both modes now use xdSegments prop when available
  const displayedXDs = new Set(
    props.xdSegments.length > 0
      ? props.xdSegments.map(xd => xd.XD)
      : props.signals.map(signal => signal.XD).filter(xd => xd !== undefined && xd !== null)
  )
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
      } else if (props.dataType === 'before-after') {
        const diff = dataValue.TTI_DIFF || 0
        fillColor = beforeAfterDifferenceColorScale(diff)
      } else if (props.dataType === 'changepoints') {
        const avgPct = dataValue.AVG_PCT_CHANGE || 0
        // avgPct is stored as decimal (0.05 = 5%), multiply by 100 for color scale
        fillColor = changepointColorScale(avgPct * 100)
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
  // Create a map of XD -> data values from xdSegments
  // Both travel-time and anomaly modes now use dedicated XD segment data
  const xdMap = new Map()

  if (props.xdSegments && props.xdSegments.length > 0) {
    // Use dedicated XD segment data (includes all dimensions + metrics)
    props.xdSegments.forEach(xd => {
      if (props.dataType === 'travel-time') {
        xdMap.set(xd.XD, {
          TRAVEL_TIME_INDEX: xd.TRAVEL_TIME_INDEX || 0,
          BEARING: xd.BEARING,
          ROADNAME: xd.ROADNAME,
          MILES: xd.MILES,
          APPROACH: xd.APPROACH
        })
      } else if (props.dataType === 'before-after') {
        // Before/After mode - include dimensions + before/after metrics
        xdMap.set(xd.XD, {
          TTI_BEFORE: xd.TTI_BEFORE || 0,
          TTI_AFTER: xd.TTI_AFTER || 0,
          TTI_DIFF: xd.TTI_DIFF || 0,
          BEARING: xd.BEARING,
          ROADNAME: xd.ROADNAME,
          MILES: xd.MILES,
          APPROACH: xd.APPROACH
        })
      } else if (props.dataType === 'changepoints') {
        // Changepoint mode - include percent change metrics and top changepoint details
        xdMap.set(xd.XD, {
          AVG_PCT_CHANGE: Number(xd.AVG_PCT_CHANGE ?? 0) || 0,
          ABS_PCT_SUM: Number(xd.ABS_PCT_SUM ?? 0) || 0,
          CHANGEPOINT_COUNT: Number(xd.CHANGEPOINT_COUNT ?? 0) || 0,
          TOP_TIMESTAMP: xd.TOP_TIMESTAMP,
          TOP_PCT_CHANGE: Number(xd.TOP_PCT_CHANGE ?? 0) || 0,
          TOP_AVG_DIFF: Number(xd.TOP_AVG_DIFF ?? 0) || 0,
          TOP_ROADNAME: xd.TOP_ROADNAME ?? xd.ROADNAME,
          TOP_BEARING: xd.TOP_BEARING ?? xd.BEARING,
          SIGNAL_ID: xd.SIGNAL_ID ?? xd.ID,
          BEARING: xd.BEARING,
          ROADNAME: xd.ROADNAME,
          MILES: xd.MILES,
          APPROACH: xd.APPROACH
        })
      } else {
        // Anomaly mode - include dimensions + anomaly metrics
        xdMap.set(xd.XD, {
          ANOMALY_COUNT: xd.ANOMALY_COUNT || 0,
          POINT_SOURCE_COUNT: xd.POINT_SOURCE_COUNT || 0,
          RECORD_COUNT: xd.RECORD_COUNT || 0,
          ANOMALY_PERCENTAGE: xd.ANOMALY_PERCENTAGE || 0,
          BEARING: xd.BEARING,
          ROADNAME: xd.ROADNAME,
          MILES: xd.MILES,
          APPROACH: xd.APPROACH
        })
      }
    })
  }

  return xdMap
}

function createXdTooltip(xd, dataValue) {
  if (!dataValue) {
    return `<div><strong>XD:</strong> ${xd}<br><em>No data</em></div>`
  }

  if (props.dataType === 'anomaly') {
    // Anomaly mode - show XD dimensions + anomaly percentage (matching TTI pattern)
    const bearing = dataValue.BEARING || 'N/A'
    const roadname = dataValue.ROADNAME || 'N/A'
    const miles = dataValue.MILES
    const approach = dataValue.APPROACH

    // Calculate anomaly percentage based on current anomaly type filter
    const countColumn = props.anomalyType === "Point Source" ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
    const count = dataValue[countColumn] || 0
    const totalRecords = dataValue.RECORD_COUNT || 0
    const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0

    return `
      <div>
        <strong>XD:</strong> ${xd}<br>
        <strong>Bearing:</strong> ${bearing}<br>
        <strong>Road:</strong> ${roadname}<br>
        <strong>Miles:</strong> ${miles !== undefined && miles !== null ? miles.toFixed(2) : 'N/A'}<br>
        <strong>Approach:</strong> ${approach ? 'Yes' : 'No'}<br>
        <strong>Anomaly %:</strong> ${percentage.toFixed(1)}%
      </div>
    `
  } else if (props.dataType === 'before-after') {
    // Before/After mode - show XD dimensions + before/after TTI values
    const ttiBefore = dataValue.TTI_BEFORE || 0
    const ttiAfter = dataValue.TTI_AFTER || 0
    const diff = dataValue.TTI_DIFF || 0
    const bearing = dataValue.BEARING || 'N/A'
    const roadname = dataValue.ROADNAME || 'N/A'
    const miles = dataValue.MILES
    const approach = dataValue.APPROACH

    return `
      <div>
        <strong>XD:</strong> ${xd}<br>
        <strong>Bearing:</strong> ${bearing}<br>
        <strong>Road:</strong> ${roadname}<br>
        <strong>Miles:</strong> ${miles !== undefined && miles !== null ? miles.toFixed(1) : 'N/A'}<br>
        <strong>Approach:</strong> ${approach ? 'Yes' : 'No'}<br>
        <strong>TTI Before:</strong> ${ttiBefore.toFixed(1)}<br>
        <strong>TTI After:</strong> ${ttiAfter.toFixed(1)}<br>
        <strong>Difference:</strong> ${diff >= 0 ? '+' : ''}${diff.toFixed(1)}
      </div>
    `
  } else if (props.dataType === 'changepoints') {
    const count = Number(dataValue.CHANGEPOINT_COUNT ?? 0) || 0
    const topPct = Number(dataValue.TOP_PCT_CHANGE ?? 0) || 0
    const topAvgDiff = Number(dataValue.TOP_AVG_DIFF ?? 0) || 0
    const topTimestamp = dataValue.TOP_TIMESTAMP ? new Date(dataValue.TOP_TIMESTAMP).toLocaleString() : 'N/A'
    const bearing = dataValue.TOP_BEARING || dataValue.BEARING || 'N/A'
    const roadname = dataValue.TOP_ROADNAME || dataValue.ROADNAME || 'N/A'

    return `
      <div>
        <strong>XD:</strong> ${xd}<br>
        <strong>Road:</strong> ${roadname}<br>
        <strong>Bearing:</strong> ${bearing}<br>
        <strong>Changepoints:</strong> ${count}<br>
        <hr />
        <strong>Top Changepoint:</strong><br>
        <strong>Percent Change:</strong> ${(topPct * 100).toFixed(1)}%<br>
        <strong>Avg Diff:</strong> ${topAvgDiff.toFixed(1)} s<br>
        <strong>Timestamp:</strong> ${topTimestamp}
      </div>
    `
  } else {
    // Travel time mode - show detailed XD segment info
    const tti = dataValue.TRAVEL_TIME_INDEX || 0
    const bearing = dataValue.BEARING || 'N/A'
    const roadname = dataValue.ROADNAME || 'N/A'
    const miles = dataValue.MILES
    const approach = dataValue.APPROACH

    return `
      <div>
        <strong>XD:</strong> ${xd}<br>
        <strong>Bearing:</strong> ${bearing}<br>
        <strong>Road:</strong> ${roadname}<br>
        <strong>Miles:</strong> ${miles !== undefined && miles !== null ? miles.toFixed(1) : 'N/A'}<br>
        <strong>Approach:</strong> ${approach ? 'Yes' : 'No'}<br>
        <strong>TTI:</strong> ${tti.toFixed(1)}
      </div>
    `
  }
}

// Select XD segments and signals that intersect with a drawn polygon
function selectXdSegmentsInPolygon(polygon) {
  console.log('🎯 selectXdSegmentsInPolygon: START', {
    polygonType: polygon.geometry.type,
    xdLayersCount: xdLayers.size,
    signalMarkersCount: signalMarkers.size
  })

  const displayedXDs = new Set(
    props.xdSegments.length > 0
      ? props.xdSegments.map(xd => xd.XD)
      : props.signals.map(signal => signal.XD).filter(xd => xd !== undefined && xd !== null)
  )
  const selectedXDs = []
  const selectedSignalIds = []

  // Check each XD layer to see if it intersects with the polygon
  xdLayers.forEach((layer, xd) => {
    // Only consider XD segments that are currently displayed (in filtered dataset)
    if (!displayedXDs.has(xd)) return

    // Get the GeoJSON of the XD layer
    const xdGeoJSON = layer.toGeoJSON()

    // Check if the XD geometry intersects with the polygon
    if (geometriesIntersect(xdGeoJSON, polygon)) {
      selectedXDs.push(xd)
    }
  })

  // Check each signal marker to see if it's inside the polygon
  signalMarkers.forEach((marker, signalId) => {
    const latLng = marker.getLatLng()
    if (pointInPolygon(latLng, polygon)) {
      selectedSignalIds.push(signalId)
    }
  })

  console.log('🎯 selectXdSegmentsInPolygon: COMPLETE', {
    selectedXDsCount: selectedXDs.length,
    selectedSignalsCount: selectedSignalIds.length,
    selectedXDs,
    selectedSignalIds
  })

  // Update selection store with selected XD segments and signals
  if (selectedXDs.length > 0 || selectedSignalIds.length > 0) {
    // Clear existing selections first
    selectionStore.clearAllSelections()

    // Add XD segments
    if (selectedXDs.length > 0) {
      selectionStore.setXdSegmentSelection(selectedXDs)
    }

    // Add signals (which will also add their associated XD segments)
    selectedSignalIds.forEach(signalId => {
      if (!selectionStore.isSignalSelected(signalId)) {
        selectionStore.toggleSignal(signalId)
      }
    })

    emit('selection-changed')
  }
}

// Helper function to check if two GeoJSON geometries intersect
function geometriesIntersect(geojson1, geojson2) {
  // Simple bounding box intersection check first (fast)
  const bounds1 = L.geoJSON(geojson1).getBounds()
  const bounds2 = L.geoJSON(geojson2).getBounds()

  if (!bounds1.intersects(bounds2)) {
    return false
  }

  // More detailed check: see if any coordinates of geojson1 are inside geojson2
  const polygon2Layer = L.geoJSON(geojson2)
  const coords1 = extractCoordinates(geojson1)

  // Check if any point from the XD segment is inside the polygon
  for (const coord of coords1) {
    const point = L.latLng(coord[1], coord[0])
    let isInside = false

    polygon2Layer.eachLayer(layer => {
      if (layer.getBounds && layer.getBounds().contains(point)) {
        // More precise point-in-polygon check
        if (layer.toGeoJSON) {
          const poly = layer.toGeoJSON()
          if (pointInPolygon(point, poly)) {
            isInside = true
          }
        }
      }
    })

    if (isInside) return true
  }

  return false
}

// Extract all coordinates from a GeoJSON geometry
function extractCoordinates(geojson) {
  const coords = []

  function traverse(geometry) {
    if (!geometry) return

    if (geometry.type === 'Point') {
      coords.push(geometry.coordinates)
    } else if (geometry.type === 'LineString') {
      coords.push(...geometry.coordinates)
    } else if (geometry.type === 'Polygon') {
      geometry.coordinates.forEach(ring => coords.push(...ring))
    } else if (geometry.type === 'MultiLineString') {
      geometry.coordinates.forEach(line => coords.push(...line))
    } else if (geometry.type === 'MultiPolygon') {
      geometry.coordinates.forEach(polygon => {
        polygon.forEach(ring => coords.push(...ring))
      })
    } else if (geometry.type === 'GeometryCollection') {
      geometry.geometries.forEach(traverse)
    } else if (geometry.type === 'Feature') {
      traverse(geometry.geometry)
    } else if (geometry.type === 'FeatureCollection') {
      geometry.features.forEach(feature => traverse(feature.geometry))
    }
  }

  traverse(geojson.geometry || geojson)
  return coords
}

// Point-in-polygon test using ray casting algorithm
function pointInPolygon(point, polygon) {
  const coords = polygon.geometry.coordinates[0] // First ring (outer boundary)
  const x = point.lng
  const y = point.lat
  let inside = false

  for (let i = 0, j = coords.length - 1; i < coords.length; j = i++) {
    const xi = coords[i][0]
    const yi = coords[i][1]
    const xj = coords[j][0]
    const yj = coords[j][1]

    const intersect = ((yi > y) !== (yj > y)) &&
      (x < (xj - xi) * (y - yi) / (yj - yi) + xi)

    if (intersect) inside = !inside
  }

  return inside
}

// Helper function to update a single marker icon only if state changed
function updateMarkerIcon(signalId, marker, category, isSelected, dataHash = null, customColor = null, options = {}) {
  const {
    iconSizeOverride = null,
    zIndexCategory = category,
    forceCircleIcon = false
  } = options

  const currentState = markerStates.get(signalId)
  const useSvg = (forceCircleIcon || customColor) ? false : shouldUseSvgIcons()
  const iconSize = iconSizeOverride ?? getMarkerSize(zIndexCategory, useSvg)

  // Check if state actually changed (including data hash, icon type, and custom color)
  if (currentState &&
      currentState.category === category &&
      currentState.isSelected === isSelected &&
      currentState.iconSize === iconSize &&
      currentState.useSvg === useSvg &&
      currentState.customColor === customColor &&
      currentState.zIndexCategory === zIndexCategory &&
      (dataHash === null || currentState.dataHash === dataHash)) {
    return false // No change needed
  }

  // State changed or new marker - update icon
  const iconStart = performance.now()
  const iconUrl = customColor
    ? createCircleIcon(category, isSelected, iconSize, customColor)
    : (useSvg
      ? createTrafficSignalIcon(category, isSelected, iconSize)
      : createCircleIcon(category, isSelected, iconSize))
  const iconGenTime = performance.now() - iconStart

  const divIconStart = performance.now()
  const iconHeight = useSvg ? iconSize * 1.4 : iconSize
  const icon = L.divIcon({
    html: `<img src="${iconUrl}" style="width: ${iconSize}px; height: ${iconHeight}px;">`,
    className: 'traffic-signal-icon',
    iconSize: [iconSize, iconHeight],
    iconAnchor: [iconSize / 2, iconHeight / 2]
  })
  const divIconTime = performance.now() - divIconStart

  const setIconStart = performance.now()
  marker.setIcon(icon)

  // Update z-index based on category (ensures red/yellow are always on top)
  const zIndexOffset = getZIndexOffset(zIndexCategory)
  marker.setZIndexOffset(zIndexOffset)

  const setIconTime = performance.now() - setIconStart

  if (setIconTime > 10) {
    console.log(`[SharedMap] SLOW setIcon for signal ${signalId}: ${setIconTime.toFixed(2)}ms`, {
      iconGenTime: iconGenTime.toFixed(2) + 'ms',
      divIconTime: divIconTime.toFixed(2) + 'ms',
      setIconTime: setIconTime.toFixed(2) + 'ms'
    })
  }

  // Update tracked state
  markerStates.set(signalId, { category, isSelected, iconSize, dataHash, useSvg, customColor, zIndexCategory })

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

  if (props.dataType === 'changepoints') {
    const { visualMap } = buildChangepointVisualMap(props.signals)

    signalMarkers.forEach((marker, signalId) => {
      const visuals = visualMap.get(signalId)
      if (!visuals) {
        return
      }

      const isSelected = selectionStore.isSignalSelected(signalId)

      const iconUpdated = updateMarkerIcon(
        signalId,
        marker,
        visuals.category,
        isSelected,
        visuals.dataHash,
        visuals.color,
        {
          iconSizeOverride: visuals.iconSize,
          forceCircleIcon: true,
          zIndexCategory: visuals.category
        }
      )

      if (iconUpdated || !marker.getTooltip()) {
        const tooltip = buildChangepointSignalTooltip(visuals)
        if (marker.getTooltip()) {
          marker.setTooltipContent(tooltip)
        } else {
          marker.bindTooltip(tooltip, {
            direction: 'top',
            offset: [0, -10]
          })
        }
      }
    })

    const perfEnd = performance.now()
    console.log(`�sT�,? updateMarkerSizes: changepoints COMPLETE in ${(perfEnd - perfStart).toFixed(2)}ms`, {
      totalMarkers: signalMarkers.size
    })
    return
  }

  const iconSize = getMarkerSize()
  console.log(`⚙️ updateMarkerSizes: iconSize = ${iconSize}`)
  let updatedCount = 0
  let findSignalTime = 0
  let getCategoryTime = 0
  let updateIconTime = 0

  // Build signal data map with aggregated values - O(n)
  const mapBuildStart = performance.now()
  const signalDataMap = new Map()
  props.signals.forEach(signal => {
    if (!signalDataMap.has(signal.ID)) {
      signalDataMap.set(signal.ID, {
        ANOMALY_COUNT: 0,
        POINT_SOURCE_COUNT: 0,
        TRAVEL_TIME_INDEX: 0,
        RECORD_COUNT: 0,
        ttiCount: 0,
        TTI_BEFORE_TOTAL: 0,
        TTI_AFTER_TOTAL: 0,
        beforeAfterCount: 0,
      })
    }
    const data = signalDataMap.get(signal.ID)
    data.ANOMALY_COUNT += (signal.ANOMALY_COUNT || 0)
    data.POINT_SOURCE_COUNT += (signal.POINT_SOURCE_COUNT || 0)
    data.TRAVEL_TIME_INDEX += (signal.TRAVEL_TIME_INDEX || 0)
    data.RECORD_COUNT += (signal.RECORD_COUNT || 0)
    data.ttiCount += 1

    if (signal.TTI_BEFORE !== undefined || signal.TTI_AFTER !== undefined || signal.TTI_DIFF !== undefined) {
      data.TTI_BEFORE_TOTAL += Number(signal.TTI_BEFORE ?? 0) || 0
      data.TTI_AFTER_TOTAL += Number(signal.TTI_AFTER ?? 0) || 0
      data.beforeAfterCount += 1
    }
  })
  const mapBuildTime = performance.now() - mapBuildStart
  console.log(`⚙️ Built signal data map in ${mapBuildTime.toFixed(2)}ms for ${props.signals.length} signals`)

  signalMarkers.forEach((marker, signalId) => {
    const isSelected = selectionStore.isSignalSelected(signalId)

    let category = 'green' // Default
    let dataHash = null
    let customColor = null
    let markerOptions

    const findStart = performance.now()
    const signalData = signalDataMap.get(signalId) // O(1) lookup
    findSignalTime += (performance.now() - findStart)

    const categoryStart = performance.now()
    if (signalData) {
      if (props.dataType === 'anomaly') {
        const countColumn = props.anomalyType === 'Point Source' ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
        const count = signalData[countColumn] || 0
        const totalRecords = signalData.RECORD_COUNT || 0
        const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0
        category = getCategoryFromValue(percentage, 'anomaly')
        // Use continuous color scale for circles (when zoomed out), but categorical for SVG signal heads
        customColor = shouldUseSvgIcons() ? null : anomalyColorScale(percentage)
        dataHash = `${count}_${totalRecords}`
      } else if (props.dataType === 'before-after' && signalData.beforeAfterCount > 0) {
        const sampleCount = signalData.beforeAfterCount
        const avgBefore = sampleCount > 0 ? signalData.TTI_BEFORE_TOTAL / sampleCount : 0
        const avgAfter = sampleCount > 0 ? signalData.TTI_AFTER_TOTAL / sampleCount : 0
        const diff = avgAfter - avgBefore

        // Categorize based on TTI difference (matching legend: -0.25, 0, +0.25)
        if (diff < -0.083) {
          category = 'green'  // Notable improvement (bottom third of range)
        } else if (diff < 0.083) {
          category = 'yellow' // Minimal change (middle third)
        } else {
          category = 'red'    // Notable degradation (top third)
        }

        // Use continuous color scale for circles (when zoomed out), but categorical for SVG signal heads
        customColor = shouldUseSvgIcons() ? null : beforeAfterDifferenceColorScale(diff)
        dataHash = `${avgBefore.toFixed(4)}_${avgAfter.toFixed(4)}`
      } else {
        const avgTTI = signalData.ttiCount > 0 ? signalData.TRAVEL_TIME_INDEX / signalData.ttiCount : 0
        category = getCategoryFromValue(avgTTI, 'travel-time')
        // Use continuous color scale for circles (when zoomed out), but categorical for SVG signal heads
        customColor = shouldUseSvgIcons() ? null : travelTimeColorScale(avgTTI)
        dataHash = `${avgTTI.toFixed(4)}_${signalData.ttiCount}`
      }
    }
    getCategoryTime += (performance.now() - categoryStart)

    const iconStart = performance.now()
    if (updateMarkerIcon(signalId, marker, category, isSelected, dataHash, customColor, markerOptions)) {
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

    // Determine icon type based on NEW signal data (not stale markers)
    const useSvgForAll = shouldUseSvgIcons(aggregatedSignals)

    // Update existing markers or create new ones
    aggregatedSignals.forEach(signal => {
      bounds.push([signal.LATITUDE, signal.LONGITUDE])

      const count = signal[countColumn] || 0
      const totalRecords = signal.RECORD_COUNT || 0
      const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0

      const category = getCategoryFromValue(percentage, 'anomaly')
      const isSelected = selectionStore.isSignalSelected(signal.ID)

      // Use continuous color scale for circles (when zoomed out), but categorical for SVG signal heads
      const customColor = useSvgForAll ? null : anomalyColorScale(percentage)
      const dataHash = `${count}_${totalRecords}`

      const existingMarker = signalMarkers.get(signal.ID)

      if (existingMarker) {
        // Update existing marker icon only if state changed
        updateMarkerIcon(signal.ID, existingMarker, category, isSelected, dataHash, customColor)

        // Update tooltip content immediately so it reflects new data
        const tooltipContent = `
          <div>
            <h4>Signal ${signal.ID}</h4>
            <p><strong>Anomaly Percentage:</strong> ${percentage.toFixed(1)}%</p>
            <p><strong>Total Anomalies:</strong> ${signal.ANOMALY_COUNT || 0}</p>
            <p><strong>Point Source:</strong> ${signal.POINT_SOURCE_COUNT || 0}</p>
            <p><strong>Approach:</strong> ${signal.APPROACH ? 'Yes' : 'No'}</p>
          </div>
        `
        if (existingMarker.getTooltip()) {
          existingMarker.setTooltipContent(tooltipContent)
        }
      } else {
        // Create new marker with appropriate icon based on viewport signal count
        const iconSize = getMarkerSize(category, useSvgForAll)
        const iconUrl = useSvgForAll
          ? createTrafficSignalIcon(category, isSelected, iconSize)
          : createCircleIcon(category, isSelected, iconSize, null, customColor)
        const iconHeight = useSvgForAll ? iconSize * 1.4 : iconSize
        const icon = L.divIcon({
          html: `<img src="${iconUrl}" style="width: ${iconSize}px; height: ${iconHeight}px;">`,
          className: 'traffic-signal-icon',
          iconSize: [iconSize, iconHeight],
          iconAnchor: [iconSize / 2, iconHeight / 2]
        })

        const zIndexOffset = getZIndexOffset(category)
        const marker = L.marker([signal.LATITUDE, signal.LONGITUDE], {
          icon: icon,
          interactive: true,
          zIndexOffset: zIndexOffset
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
  } else if (props.dataType === 'changepoints') {
    const signalsWithCoords = props.signals.filter(signal => {
      const lat = Number(signal.LATITUDE)
      const lng = Number(signal.LONGITUDE)
      return Number.isFinite(lat) && Number.isFinite(lng)
    })

    if (signalsWithCoords.length === 0) {
      markersLayer.clearLayers()
      signalMarkers.clear()
      markerStates.clear()
      return
    }

    const { visualMap } = buildChangepointVisualMap(signalsWithCoords)
    const newSignalIds = new Set([...visualMap.keys()])

    const markersToRemove = []
    signalMarkers.forEach((marker, signalId) => {
      if (!newSignalIds.has(signalId)) {
        markersToRemove.push(signalId)
      }
    })

    markersToRemove.forEach(signalId => {
      const marker = signalMarkers.get(signalId)
      if (marker) {
        markersLayer.removeLayer(marker)
        signalMarkers.delete(signalId)
        markerStates.delete(signalId)
      }
    })

    visualMap.forEach((visuals, signalId) => {
      const signal = visuals.signal
      bounds.push([signal.LATITUDE, signal.LONGITUDE])
      const isSelected = selectionStore.isSignalSelected(signalId)
      const tooltipContent = buildChangepointSignalTooltip(visuals)
      const existingMarker = signalMarkers.get(signalId)

      if (existingMarker) {
        updateMarkerIcon(
          signalId,
          existingMarker,
          visuals.category,
          isSelected,
          visuals.dataHash,
          visuals.color,
          {
            iconSizeOverride: visuals.iconSize,
            forceCircleIcon: true,
            zIndexCategory: visuals.category
          }
        )

        if (existingMarker.getTooltip()) {
          existingMarker.setTooltipContent(tooltipContent)
        } else {
          existingMarker.bindTooltip(tooltipContent, {
            direction: 'top',
            offset: [0, -10]
          })
        }
      } else {
        const placeholderIcon = L.divIcon({
          html: '<div></div>',
          className: 'traffic-signal-icon',
          iconSize: [visuals.iconSize, visuals.iconSize],
          iconAnchor: [visuals.iconSize / 2, visuals.iconSize / 2]
        })

        const marker = L.marker([signal.LATITUDE, signal.LONGITUDE], {
          icon: placeholderIcon,
          interactive: true
        })

        updateMarkerIcon(
          signalId,
          marker,
          visuals.category,
          isSelected,
          visuals.dataHash,
          visuals.color,
          {
            iconSizeOverride: visuals.iconSize,
            forceCircleIcon: true,
            zIndexCategory: visuals.category
          }
        )

        marker.bindTooltip(tooltipContent, {
          direction: 'top',
          offset: [0, -10]
        })

        marker.on('click', (e) => {
          L.DomEvent.stopPropagation(e)
          selectionStore.toggleSignal(signalId)
          emit('selection-changed')
        })

        markersLayer.addLayer(marker)
        signalMarkers.set(signalId, marker)
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
          NAME: signal.NAME,  // Include NAME from backend
          LATITUDE: latitude,
          LONGITUDE: longitude,
          TRAVEL_TIME_INDEX: Number(signal.TRAVEL_TIME_INDEX ?? 0) || 0,
          ttiCount: 1  // Backend now pre-aggregates, so typically 1 row per signal
        })
      } else {
        // Handle legacy case where signal appears multiple times (shouldn't happen with new backend)
        const group = signalGroups.get(signal.ID)
        const tti = Number(signal.TRAVEL_TIME_INDEX ?? 0) || 0
        group.TRAVEL_TIME_INDEX += tti
        group.ttiCount += 1
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

    // Determine icon type based on NEW signal data (not stale markers)
    const useSvgForAll = shouldUseSvgIcons(aggregatedSignals)

    // Update existing markers or create new ones
    aggregatedSignals.forEach(signal => {
      bounds.push([signal.LATITUDE, signal.LONGITUDE])

      // Calculate average TTI for coloring
      const avgTTI = signal.ttiCount > 0
        ? signal.TRAVEL_TIME_INDEX / signal.ttiCount
        : 0

      const category = getCategoryFromValue(avgTTI, 'travel-time')
      const isSelected = selectionStore.isSignalSelected(signal.ID)

      // Use continuous color scale for circles (when zoomed out), but categorical for SVG signal heads
      const customColor = useSvgForAll ? null : travelTimeColorScale(avgTTI)
      const dataHash = `${avgTTI.toFixed(4)}_${signal.ttiCount}`

      const existingMarker = signalMarkers.get(signal.ID)

      if (existingMarker) {
        // Update existing marker icon only if state changed
        updateMarkerIcon(signal.ID, existingMarker, category, isSelected, dataHash, customColor)

        // Update tooltip content immediately so it reflects new data
        // Skip for before-after mode - applyBeforeAfterStyling() handles it
        if (props.dataType !== 'before-after') {
          const ttiDisplay = Number.isFinite(avgTTI) ? avgTTI.toFixed(2) : 'N/A'
          const signalName = signal.NAME || `Signal ${signal.ID}`
          const tooltipContent = `
            <div>
              <h4>${signalName}</h4>
              <p><strong>Travel Time Index:</strong> ${ttiDisplay}</p>
            </div>
          `
          if (existingMarker.getTooltip()) {
            existingMarker.setTooltipContent(tooltipContent)
          }
        }
      } else {
        // Create new marker with appropriate icon based on viewport signal count
        const iconSize = getMarkerSize(category, useSvgForAll)
        const iconUrl = useSvgForAll
          ? createTrafficSignalIcon(category, isSelected, iconSize)
          : createCircleIcon(category, isSelected, iconSize, null, customColor)
        const iconHeight = useSvgForAll ? iconSize * 1.4 : iconSize
        const icon = L.divIcon({
          html: `<img src="${iconUrl}" style="width: ${iconSize}px; height: ${iconHeight}px;">`,
          className: 'traffic-signal-icon',
          iconSize: [iconSize, iconHeight],
          iconAnchor: [iconSize / 2, iconHeight / 2]
        })

        const zIndexOffset = getZIndexOffset(category)
        const marker = L.marker([signal.LATITUDE, signal.LONGITUDE], {
          icon: icon,
          interactive: true,
          zIndexOffset: zIndexOffset
        })

        const ttiDisplay = Number.isFinite(avgTTI) ? avgTTI.toFixed(2) : 'N/A'
        const signalName = signal.NAME || `Signal ${signal.ID}`

        const tooltipContent = `
          <div>
            <h4>${signalName}</h4>
            <p><strong>Travel Time Index:</strong> ${ttiDisplay}</p>
          </div>
        `

        marker.bindTooltip(tooltipContent, {
          direction: 'top',
          offset: [0, -10]
        })

        // Lazy tooltip update on mouseover
        // Skip for before-after mode - applyBeforeAfterStyling() handles it
        if (props.dataType !== 'before-after') {
          marker.on('mouseover', () => {
            // Get current signal from props (which has NAME and already aggregated TTI)
            const currentSignal = props.signals.find(s => s.ID === signal.ID)
            if (currentSignal) {
              const currentTTI = Number(currentSignal.TRAVEL_TIME_INDEX ?? 0) || 0
              const currentTtiDisplay = Number.isFinite(currentTTI) ? currentTTI.toFixed(2) : 'N/A'
              const currentName = currentSignal.NAME || `Signal ${currentSignal.ID}`

              const updatedTooltip = `
                <div>
                  <h4>${currentName}</h4>
                  <p><strong>Travel Time Index:</strong> ${currentTtiDisplay}</p>
                </div>
              `
              marker.setTooltipContent(updatedTooltip)
            }
          })
        }

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

  if (props.dataType === 'before-after') {
    applyBeforeAfterStyling()
  }
}

function applyBeforeAfterStyling() {
  const aggregated = new Map()

  props.signals.forEach(signal => {
    const latitude = Number(signal.LATITUDE)
    const longitude = Number(signal.LONGITUDE)
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      return
    }

    if (!aggregated.has(signal.ID)) {
      aggregated.set(signal.ID, {
        ID: signal.ID,
        NAME: signal.NAME,
        LATITUDE: latitude,
        LONGITUDE: longitude,
        TTI_BEFORE_TOTAL: 0,
        TTI_AFTER_TOTAL: 0,
        count: 0
      })
    }

    const entry = aggregated.get(signal.ID)
    entry.TTI_BEFORE_TOTAL += Number(signal.TTI_BEFORE ?? 0) || 0
    entry.TTI_AFTER_TOTAL += Number(signal.TTI_AFTER ?? 0) || 0
    entry.count += 1
  })

  signalMarkers.forEach((marker, signalId) => {
    const data = aggregated.get(signalId)
    if (!data) {
      return
    }

    const avgBefore = data.count > 0 ? data.TTI_BEFORE_TOTAL / data.count : 0
    const avgAfter = data.count > 0 ? data.TTI_AFTER_TOTAL / data.count : 0
    const diff = avgAfter - avgBefore

    // Categorize based on TTI difference (matching legend: -0.25, 0, +0.25)
    let category
    if (diff < -0.083) {
      category = 'green'  // Notable improvement (bottom third of range)
    } else if (diff < 0.083) {
      category = 'yellow' // Minimal change (middle third)
    } else {
      category = 'red'    // Notable degradation (top third)
    }

    // Use continuous color scale for circles (when zoomed out), but categorical for SVG signal heads
    const customColor = shouldUseSvgIcons() ? null : beforeAfterDifferenceColorScale(diff)
    const isSelected = selectionStore.isSignalSelected(signalId)
    const dataHash = `${avgBefore.toFixed(4)}_${avgAfter.toFixed(4)}`

    updateMarkerIcon(signalId, marker, category, isSelected, dataHash, customColor)

    const displayName = data.NAME || `Signal ${signalId}`
    const tooltipContent = `
      <div>
        <h4>${displayName}</h4>
        <p><strong>Before TTI:</strong> ${Number.isFinite(avgBefore) ? avgBefore.toFixed(2) : 'N/A'}</p>
        <p><strong>After TTI:</strong> ${Number.isFinite(avgAfter) ? avgAfter.toFixed(2) : 'N/A'}</p>
        <p><strong>Difference:</strong> ${Number.isFinite(diff) ? diff.toFixed(2) : 'N/A'}</p>
      </div>
    `

    if (marker.getTooltip()) {
      marker.setTooltipContent(tooltipContent)
    } else {
      marker.bindTooltip(tooltipContent, {
        direction: 'top',
        offset: [0, -10]
      })
    }
  })
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
    const displayedXDs = new Set(
      props.xdSegments.length > 0
        ? props.xdSegments.map(xd => xd.XD)
        : props.signals.map(signal => signal.XD).filter(xd => xd !== undefined && xd !== null)
    )
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
  // Theme-aware selection colors
  const isDark = themeStore.currentTheme === 'dark'
  const selectionColor = isDark ? '#FFFFFF' : '#000000'

  // Build aggregated data map for quick lookups
  const signalDataMap = new Map()
  let changepointVisualMap = null

  if (props.dataType === 'changepoints') {
    changepointVisualMap = buildChangepointVisualMap(props.signals).visualMap
  } else {
    props.signals.forEach(signal => {
      if (!signalDataMap.has(signal.ID)) {
        signalDataMap.set(signal.ID, {
          ANOMALY_COUNT: 0,
          POINT_SOURCE_COUNT: 0,
          TRAVEL_TIME_INDEX: 0,
          RECORD_COUNT: 0,
          ttiCount: 0,
          TTI_BEFORE_TOTAL: 0,
          TTI_AFTER_TOTAL: 0,
          beforeAfterCount: 0
        })
      }
      const data = signalDataMap.get(signal.ID)
      data.ANOMALY_COUNT += (signal.ANOMALY_COUNT || 0)
      data.POINT_SOURCE_COUNT += (signal.POINT_SOURCE_COUNT || 0)
      data.TRAVEL_TIME_INDEX += (signal.TRAVEL_TIME_INDEX || 0)
      data.RECORD_COUNT += (signal.RECORD_COUNT || 0)
      data.ttiCount += 1

      if (signal.TTI_BEFORE !== undefined || signal.TTI_AFTER !== undefined || signal.TTI_DIFF !== undefined) {
        data.TTI_BEFORE_TOTAL += Number(signal.TTI_BEFORE ?? 0) || 0
        data.TTI_AFTER_TOTAL += Number(signal.TTI_AFTER ?? 0) || 0
        data.beforeAfterCount += 1
      }
    })
  }

  let updatedCount = 0

  signalMarkers.forEach((marker, signalId) => {
    const isSelected = selectionStore.isSignalSelected(signalId)
    const signalData = signalDataMap.get(signalId)

    if (props.dataType === 'changepoints' && changepointVisualMap) {
      const visuals = changepointVisualMap.get(signalId)
      if (visuals) {
        if (updateMarkerIcon(
          signalId,
          marker,
          visuals.category,
          isSelected,
          visuals.dataHash,
          visuals.color,
          {
            iconSizeOverride: visuals.iconSize,
            forceCircleIcon: true,
            zIndexCategory: visuals.category
          }
        )) {
          updatedCount++
        }
      }
      return
    }

    if (props.dataType === 'anomaly' && signalData) {
      const countColumn = props.anomalyType === 'Point Source' ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
      const count = signalData[countColumn] || 0
      const totalRecords = signalData.RECORD_COUNT || 0
      const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0
      const category = getCategoryFromValue(percentage, 'anomaly')
      const dataHash = `${count}_${totalRecords}`
      if (updateMarkerIcon(signalId, marker, category, isSelected, dataHash)) {
        updatedCount++
      }
    } else if (props.dataType === 'before-after' && signalData && signalData.beforeAfterCount > 0) {
      const sampleCount = signalData.beforeAfterCount
      const avgBefore = sampleCount > 0 ? signalData.TTI_BEFORE_TOTAL / sampleCount : 0
      const avgAfter = sampleCount > 0 ? signalData.TTI_AFTER_TOTAL / sampleCount : 0
      const diff = avgAfter - avgBefore

      // Categorize based on TTI difference (matching legend: -0.25, 0, +0.25)
      let category
      if (diff < -0.083) {
        category = 'green'  // Notable improvement (bottom third of range)
      } else if (diff < 0.083) {
        category = 'yellow' // Minimal change (middle third)
      } else {
        category = 'red'    // Notable degradation (top third)
      }

      // Use continuous color scale for circles (when zoomed out), but categorical for SVG signal heads
      const customColor = shouldUseSvgIcons() ? null : beforeAfterDifferenceColorScale(diff)
      const dataHash = `${avgBefore.toFixed(4)}_${avgAfter.toFixed(4)}`
      if (updateMarkerIcon(signalId, marker, category, isSelected, dataHash, customColor)) {
        updatedCount++
      }
    } else {
      const avgTTI = signalData && signalData.ttiCount > 0
        ? signalData.TRAVEL_TIME_INDEX / signalData.ttiCount
        : 0
      const category = getCategoryFromValue(avgTTI, 'travel-time')
      const dataHash = `${avgTTI.toFixed(4)}_${signalData ? signalData.ttiCount : 0}`
      if (updateMarkerIcon(signalId, marker, category, isSelected, dataHash)) {
        updatedCount++
      }
    }
  })

  if (DEBUG_FRONTEND_LOGGING && updatedCount > 0) {
    console.log(`[SharedMap] updateSelectionStyles: Updated ${updatedCount}/${signalMarkers.size} markers`)
  }

  const displayedXDs = new Set(
    props.xdSegments.length > 0
      ? props.xdSegments.map(xd => xd.XD)
      : props.signals.map(signal => signal.XD).filter(xd => xd !== undefined && xd !== null)
  )

  const xdDataMap = getXdDataMap()

  xdLayers.forEach((layer, xd) => {
    const isSelected = selectionStore.isXdSegmentSelected(xd)
    const isInFilteredSet = displayedXDs.has(xd)
    const dataValue = xdDataMap.get(xd)

    let fillColor = '#cccccc'

    if (isInFilteredSet && dataValue !== undefined && dataValue !== null) {
      if (props.dataType === 'anomaly') {
        const countColumn = props.anomalyType === 'Point Source' ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
        const count = dataValue[countColumn] || 0
        const totalRecords = dataValue.RECORD_COUNT || 0
        const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0
        fillColor = anomalyColorScale(percentage)
      } else if (props.dataType === 'before-after') {
        const diff = dataValue.TTI_DIFF || 0
        fillColor = beforeAfterDifferenceColorScale(diff)
      } else {
        const tti = dataValue.TRAVEL_TIME_INDEX || 0
        fillColor = travelTimeColorScale(tti)
      }
    }

    const styleUpdate = {
      color: isSelected ? selectionColor : (isInFilteredSet ? fillColor : '#808080'),
      weight: isSelected ? 3 : 1,
      opacity: isSelected ? 1 : (isInFilteredSet ? 0.8 : 0.3),
      fillColor: isInFilteredSet ? fillColor : '#cccccc',
      fillOpacity: isInFilteredSet ? (isSelected ? 0.7 : 0.6) : 0.2
    }

    layer.eachLayer(childLayer => {
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
