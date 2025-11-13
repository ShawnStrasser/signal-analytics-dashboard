<template>
  <div class="anomalies-view">
    <!-- Page Title with Legend -->
    <v-card class="mb-3">
      <v-card-title class="py-2 d-flex align-center flex-wrap">
        <div class="d-flex align-center">
          <v-icon left>mdi-alert</v-icon>
          <span>Anomaly Analysis</span>
        </div>
        <v-spacer class="d-none d-sm-flex"></v-spacer>
        <div class="legend-container d-flex align-center flex-wrap mt-2 mt-sm-0">
          <span class="text-caption font-weight-medium mr-2 d-none d-sm-inline">Legend:</span>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendGreenColor }"></div>
            <span class="legend-text"><span class="d-none d-sm-inline">Low </span>0%</span>
          </div>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendYellowColor }"></div>
            <span class="legend-text"><span class="d-none d-sm-inline">Med </span>5%</span>
          </div>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendRedColor }"></div>
            <span class="legend-text"><span class="d-none d-sm-inline">High </span>10%</span>
          </div>
        </div>
      </v-card-title>
    </v-card>

    <!-- Main Content Area with Dynamic Height -->
    <div class="content-grid">
      <!-- Map Section -->
      <v-card class="map-card">
        <v-card-title class="py-2 d-flex align-center flex-wrap">
          <div class="d-flex align-center">
            🗺️ Anomaly Distribution Map
            <span class="map-instruction ml-2 text-medium-emphasis d-none d-md-inline">— Click signals or segments to filter the chart.</span>
          </div>
          <v-spacer></v-spacer>
          <div v-if="selectionStore.hasMapSelections" class="d-flex align-center gap-2 flex-wrap">
            <v-chip size="small" color="info" variant="tonal" class="selection-chip">
              <span v-if="selectionStore.selectedSignals.size > 0">
                {{ selectionStore.selectedSignals.size }} signal(s)
              </span>
              <span v-if="selectionStore.selectedSignals.size > 0 && selectionStore.selectedXdSegments.size > 0"> • </span>
              <span v-if="selectionStore.selectedXdSegments.size > 0">
                {{ selectionStore.selectedXdSegments.size }} XD segment(s)
              </span>
            </v-chip>
            <v-btn
              size="small"
              variant="outlined"
              color="error"
              @click="clearMapSelections"
            >
              Clear Map Selections
            </v-btn>
          </div>
        </v-card-title>
        <v-card-text class="map-container">
          <SharedMap
            ref="mapRef"
            v-if="mapData.length > 0"
            :signals="mapData"
            :xd-segments="xdData"
            :auto-zoom-enabled="shouldAutoZoomMap"
            data-type="anomaly"
            :anomaly-type="filtersStore.anomalyType"
            @selection-changed="onSelectionChanged"
          />
          <div v-if="mapIsLoading && showMapSpinner" class="d-flex justify-center align-center loading-overlay">
            <v-progress-circular indeterminate size="64"></v-progress-circular>
          </div>
          <div v-else-if="!mapIsLoading && mapData.length === 0" class="d-flex justify-center align-center loading-overlay">
            <div class="text-h5 text-grey">NO DATA</div>
          </div>
        </v-card-text>
      </v-card>

      <!-- Chart Section -->
      <v-card class="chart-card">
        <v-card-title class="py-2 d-flex align-center flex-wrap">
          📈 Travel Time Analysis with Anomaly Detection
          <v-spacer></v-spacer>
          <div class="d-flex align-center flex-wrap gap-2">
            <v-select
              v-model="legendBy"
              :items="legendOptions"
              label="Legend"
              density="compact"
              variant="outlined"
              hide-details
              style="max-width: 200px;"
            ></v-select>
            <v-btn-toggle
              v-model="chartMode"
              mandatory
              density="compact"
              color="primary"
            >
              <v-btn value="percent" size="small">
                Percent Anomaly
              </v-btn>
              <v-btn value="forecast" size="small">
                Forecast vs Actual
              </v-btn>
            </v-btn-toggle>
          </div>
        </v-card-title>
        <v-card-subtitle v-if="legendClipped" class="py-1">
          <v-alert density="compact" variant="outlined" color="orange-darken-2" icon="mdi-alert-circle-outline">
            <strong>Maximum legend items reached ({{ maxLegendEntities }})</strong> — Only the first {{ maxLegendEntities }} {{ legendByLabel }} are displayed.
            To see other {{ legendByLabel }}, try filtering by date range, signal selection, or map selection.
          </v-alert>
        </v-card-subtitle>
        <v-card-text class="chart-container">
          <AnomalyChart
            v-if="chartData.length > 0"
            :data="chartData"
            :chart-mode="chartMode"
            :legend-by="legendBy"
          />
          <div v-if="chartIsLoading && showChartSpinner" class="d-flex justify-center align-center loading-overlay">
            <v-progress-circular indeterminate size="64"></v-progress-circular>
          </div>
          <div v-else-if="!chartIsLoading && chartData.length === 0" class="d-flex justify-center align-center loading-overlay">
            <div class="text-h5 text-grey">NO DATA</div>
          </div>
        </v-card-text>
      </v-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onActivated, onDeactivated } from 'vue'
import { useFiltersStore } from '@/stores/filters'
import { useSelectionStore } from '@/stores/selection'
import { useSignalDimensionsStore } from '@/stores/signalDimensions'
import { useXdDimensionsStore } from '@/stores/xdDimensions'
import { useThemeStore } from '@/stores/theme'
import ApiService from '@/services/api'
import SharedMap from '@/components/SharedMap.vue'
import AnomalyChart from '@/components/AnomalyChart.vue'
import { useDelayedBoolean } from '@/utils/useDelayedBoolean'

const filtersStore = useFiltersStore()
const selectionStore = useSelectionStore()
const signalDimensionsStore = useSignalDimensionsStore()
const xdDimensionsStore = useXdDimensionsStore()
const themeStore = useThemeStore()

// Computed legend colors based on colorblind mode
const legendGreenColor = computed(() => themeStore.colorblindMode ? '#0072B2' : '#4caf50')
const legendYellowColor = computed(() => themeStore.colorblindMode ? '#F0E442' : '#ffc107')
const legendRedColor = computed(() => themeStore.colorblindMode ? '#D55E00' : '#d32f2f')
const mapData = ref([])
const xdData = ref([])  // XD segment data for map tooltips/coloring
const chartData = ref([])
const mapRef = ref(null)
const loadingMap = ref(true)
const loadingChart = ref(true)
const loading = ref(true) // Global loading state
const chartMode = ref('forecast') // 'forecast' or 'percent'
const legendBy = ref('none') // Legend grouping selection
const legendClipped = ref(false) // Whether legend entities were clipped
const maxLegendEntities = ref(6) // Max legend entities for anomaly charts (each entity has 2 lines)
const shouldAutoZoomMap = ref(true) // Controls whether the map auto-zooms on data refresh

const mapIsLoading = computed(() => loading.value || loadingMap.value)
const chartIsLoading = computed(() => loading.value || loadingChart.value)
const showMapSpinner = useDelayedBoolean(mapIsLoading)
const showChartSpinner = useDelayedBoolean(chartIsLoading)

// Track last known selection state to detect changes when page reactivates
const lastSelectionState = ref(null)

function captureSelectionState() {
  return {
    signalsSize: selectionStore.selectedSignals.size,
    xdSegmentsSize: selectionStore.selectedXdSegments.size,
    signals: Array.from(selectionStore.selectedSignals).sort().join(','),
    xdSegments: Array.from(selectionStore.selectedXdSegments).sort().join(',')
  }
}

// Legend options for the dropdown
const legendOptions = [
  { title: 'None', value: 'none' },
  { title: 'XD Segment', value: 'xd' },
  { title: 'Bearing', value: 'bearing' },
  { title: 'County', value: 'county' },
  { title: 'Road Name', value: 'roadname' },
  { title: 'Signal ID', value: 'id' }
]

// Computed label for legend clipping message
const legendByLabel = computed(() => {
  const labels = {
    'xd': 'XD segments',
    'bearing': 'bearings',
    'county': 'counties',
    'roadname': 'road names',
    'id': 'signal IDs'
  }
  return labels[legendBy.value] || 'items'
})

// Table removed - see plan for details

// Watch for geometry/signal/anomaly filter changes (triggers auto-zoom)
watch(() => [
  filtersStore.selectedSignalIds,
  filtersStore.maintainedBy,
  filtersStore.approach,
  filtersStore.validGeometry,
  filtersStore.anomalyType
], async () => {
  if (loading.value) {
    console.log('⏸️ Already loading - skipping filter change')
    return
  }

  shouldAutoZoomMap.value = true
  console.log('🔄 Geometry/anomaly filters changed - reloading with auto-zoom')
  loading.value = true
  try {
    // Reset map selections when these filters change
    if (selectionStore.hasMapSelections) {
      selectionStore.clearAllSelections()
    }

    // Reload data (map will auto-zoom via SharedMap watch)
    await Promise.all([
      loadMapData(),
      loadChartData()
    ])
  } finally {
    loading.value = false
  }
}, { deep: true })

// Watch for date/time filter changes only (no auto-zoom needed)
watch(() => [
  filtersStore.startDate,
  filtersStore.endDate,
  filtersStore.startHour,
  filtersStore.startMinute,
  filtersStore.endHour,
  filtersStore.endMinute,
  filtersStore.timeFilterEnabled,
  filtersStore.dayOfWeek
], async () => {
  if (loading.value) {
    console.log('⏸️ Already loading - skipping filter change')
    return
  }

  shouldAutoZoomMap.value = false
  console.log('📅 Date/time filters changed - reloading data only (no zoom)')
  loading.value = true
  try {
    // Don't reset selections on date changes - just refresh data
    await Promise.all([
      loadMapData(),
      loadChartData()
    ])
  } finally {
    loading.value = false
  }
})

// Watch for selection changes - reload chart data only
// Watch the Set sizes and allSelectedXdSegments size to detect changes
watch(() => [
  selectionStore.selectedSignals.size,
  selectionStore.selectedXdSegments.size,
  selectionStore.allSelectedXdSegments.size
], async () => {
  console.log('Selection changed - reloading chart data')
  await loadChartData()
})

// Watch for chart mode changes
watch(chartMode, async () => {
  console.log('📊 Chart mode changed - reloading chart data')
  await loadChartData()
})

// Watch for legend selection changes
watch(legendBy, async () => {
  console.log('🏷️ Legend selection changed - reloading chart data')
  await loadChartData()
})

onMounted(async () => {
  const t0 = performance.now()
  console.log('🚀 Anomalies.vue: onMounted START')

  // Fetch config first
  const config = await ApiService.getConfig()
  maxLegendEntities.value = config.maxAnomalyLegendEntities

  // Load dimension data first (once per session)
  // These are cached and won't be re-queried on filter changes
  await Promise.all([
    signalDimensionsStore.loadDimensions(),
    xdDimensionsStore.loadDimensions()
  ])
  const t1 = performance.now()
  console.log(`📊 Dimensions loaded in ${(t1 - t0).toFixed(2)}ms`)

  // Load map and chart data (metrics only - will be merged with dimensions)
  loading.value = true
  try {
    await Promise.all([
      loadMapData(),
      loadChartData()
    ])
  } finally {
    loading.value = false
  }

  const t2 = performance.now()
  console.log(`✅ Anomalies.vue: onMounted COMPLETE, total ${(t2 - t0).toFixed(2)}ms`)
})

onActivated(async () => {
  console.log('🔄 Anomalies.vue: onActivated')

  const currentState = captureSelectionState()

  // Check if selections changed while we were away
  const selectionsChanged = !lastSelectionState.value ||
    currentState.signalsSize !== lastSelectionState.value.signalsSize ||
    currentState.xdSegmentsSize !== lastSelectionState.value.xdSegmentsSize ||
    currentState.signals !== lastSelectionState.value.signals ||
    currentState.xdSegments !== lastSelectionState.value.xdSegments

  if (selectionsChanged) {
    console.log('🔄 Selections changed while away - reloading chart data', {
      old: lastSelectionState.value,
      new: currentState
    })
    // Set loading state to hide chart during refresh
    loading.value = true
    try {
      await loadChartData()
    } finally {
      loading.value = false
    }
  } else {
    console.log('🔄 Selections unchanged - no chart reload needed')
  }
})

onDeactivated(() => {
  console.log('🔄 Anomalies.vue: onDeactivated - capturing selection state')
  // Capture state when leaving the page so we can detect changes on return
  lastSelectionState.value = captureSelectionState()
})

async function loadMapData() {
  try {
    console.log('📡 API: Loading map data START', filtersStore.filterParams)
    const t0 = performance.now()
    loadingMap.value = true

    // Fetch both signal-level and XD-level METRICS ONLY (no dimensions)
    const [signalTable, xdTable] = await Promise.all([
      ApiService.getAnomalySummary(filtersStore.filterParams),
      ApiService.getAnomalySummaryXd(filtersStore.filterParams)
    ])

    const t1 = performance.now()
    console.log(`📡 API: Parallel fetch took ${(t1 - t0).toFixed(2)}ms`)

    // Convert Arrow tables to objects (metrics only)
    const conversionStart = performance.now()
    const signalMetrics = ApiService.arrowTableToObjects(signalTable)
    const xdMetrics = ApiService.arrowTableToObjects(xdTable)
    const t2 = performance.now()
    console.log(`📡 API: arrowTableToObjects (both) took ${(t2 - conversionStart).toFixed(2)}ms`)

    // Merge metrics with cached dimensions
    const mergeStart = performance.now()

    // Merge signal metrics with dimensions
    const signalObjects = signalMetrics.map(metric => {
      const dimensions = signalDimensionsStore.getSignalDimensions(metric.ID)

      // Calculate anomaly percentage
      const countColumn = filtersStore.anomalyType === "Point Source" ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
      const count = metric[countColumn] || 0
      const totalRecords = metric.RECORD_COUNT || 0
      const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0

      return {
        ID: metric.ID,
        ANOMALY_COUNT: metric.ANOMALY_COUNT,
        POINT_SOURCE_COUNT: metric.POINT_SOURCE_COUNT,
        RECORD_COUNT: metric.RECORD_COUNT,
        ANOMALY_PERCENTAGE: percentage,
        NAME: dimensions?.NAME || `Signal ${metric.ID}`,
        LATITUDE: dimensions?.LATITUDE,
        LONGITUDE: dimensions?.LONGITUDE
      }
    })
    .filter(signal => signal.LATITUDE && signal.LONGITUDE) // Only include signals with coordinates
    .filter(signal => signal.ANOMALY_PERCENTAGE > 0) // Filter out signals with 0% anomalies

    // Merge XD metrics with dimensions
    const xdObjects = xdMetrics.map(metric => {
      const dimensions = xdDimensionsStore.getXdDimensions(metric.XD)
      const signalIds = dimensions?.signalIds ?? (dimensions?.ID ? [dimensions.ID] : [])

      // Calculate anomaly percentage
      const countColumn = filtersStore.anomalyType === "Point Source" ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
      const count = metric[countColumn] || 0
      const totalRecords = metric.RECORD_COUNT || 0
      const percentage = totalRecords > 0 ? (count / totalRecords) * 100 : 0

      return {
        XD: metric.XD,
        ANOMALY_COUNT: metric.ANOMALY_COUNT,
        POINT_SOURCE_COUNT: metric.POINT_SOURCE_COUNT,
        RECORD_COUNT: metric.RECORD_COUNT,
        ANOMALY_PERCENTAGE: percentage,
        ID: dimensions?.ID ?? signalIds[0],
        BEARING: dimensions?.BEARING,
        ROADNAME: dimensions?.ROADNAME,
        MILES: dimensions?.MILES,
        APPROACH: dimensions?.APPROACH,
        signalIds
      }
    })

    const t3 = performance.now()
    console.log(`📡 API: Dimension merge took ${(t3 - mergeStart).toFixed(2)}ms`)

    // Assign to refs
    mapData.value = signalObjects
    xdData.value = xdObjects
    const t4 = performance.now()

    console.log(`📡 API: Loading map data DONE - ${mapData.value.length} signals, ${xdData.value.length} XDs in ${(t4 - t0).toFixed(2)}ms`)
  } catch (error) {
    console.error('Failed to load map data:', error)
    mapData.value = []
    xdData.value = []
  } finally {
    loadingMap.value = false
  }
}

async function loadChartData() {
  try {
    console.log('📊 API: Loading chart data START')
    const t0 = performance.now()
    loadingChart.value = true

    // Build filter params for chart based on selections
    const filters = { ...filtersStore.filterParams }

    // If there are map selections, send the selected XD segments directly
    if (selectionStore.hasMapSelections) {
      const selectedXds = Array.from(selectionStore.allSelectedXdSegments)

      if (selectedXds.length > 0) {
        filters.xd_segments = selectedXds
        console.log('📊 API: Filtering chart to selected XDs', selectedXds)
      } else {
        // No selections, show empty chart
        console.log('📊 API: No XD selections, showing empty chart')
        chartData.value = []
        return
      }
    }

    // Use different API based on chart mode
    let arrowTable
    let t1
    if (chartMode.value === 'percent') {
      // Percent Anomaly mode
      arrowTable = await ApiService.getAnomalyPercentAggregated(filters, legendBy.value)
      t1 = performance.now()
      console.log(`📊 API: getAnomalyPercentAggregated took ${(t1 - t0).toFixed(2)}ms`)
    } else {
      // Forecast vs Actual mode
      arrowTable = await ApiService.getAnomalyAggregated(filters, legendBy.value)
      t1 = performance.now()
      console.log(`📊 API: getAnomalyAggregated took ${(t1 - t0).toFixed(2)}ms`)
    }

    const data = ApiService.arrowTableToObjects(arrowTable)

    // Check if data contains LEGEND_GROUP column (indicates legend grouping is active)
    if (data.length > 0 && data[0].LEGEND_GROUP !== undefined) {
      // Count unique legend groups to detect if we hit the MAX_LEGEND_ENTITIES limit
      const uniqueGroups = new Set(data.map(row => row.LEGEND_GROUP))
      // Show warning when we have exactly maxLegendEntities groups
      legendClipped.value = uniqueGroups.size === maxLegendEntities.value
      console.log('🚨 Anomalies legendClipped check:', {
        uniqueGroupsSize: uniqueGroups.size,
        maxLegendEntities: maxLegendEntities.value,
        legendClipped: legendClipped.value,
        uniqueGroupsSample: Array.from(uniqueGroups).slice(0, 3)
      })
    } else {
      legendClipped.value = false
      console.log('🚨 Anomalies legendClipped: no LEGEND_GROUP column, legendClipped = false')
    }

    chartData.value = data
    const t2 = performance.now()
    console.log(`📊 API: arrowTableToObjects took ${(t2 - t1).toFixed(2)}ms`)
    console.log(`📊 API: Loading chart data DONE - ${chartData.value.length} records in ${(t2 - t0).toFixed(2)}ms`)
  } catch (error) {
    console.error('Failed to load chart data:', error)
    chartData.value = []
  } finally {
    loadingChart.value = false
  }
}

function onSelectionChanged() {
  // Selection changed via map interaction - chart will auto-update via watcher
}

function clearMapSelections() {
  selectionStore.clearAllSelections()
}
</script>

<style scoped>
.anomalies-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.content-grid {
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 12px;
  flex: 1;
  min-height: 0; /* Critical for grid to respect parent height */
}

.map-card,
.chart-card {
  display: flex;
  flex-direction: column;
  min-height: 0; /* Allow cards to shrink */
  overflow: hidden;
}

.map-container,
.chart-container {
  flex: 1;
  position: relative;
  min-height: 0; /* Allow containers to shrink */
  padding: 12px !important;
}

.loading-overlay {
  height: 100%;
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.8);
  z-index: 1000;
}

/* Mobile optimizations */
@media (max-width: 960px) {
  .content-grid {
    grid-template-rows: auto auto;
    gap: 8px;
  }

  .map-container,
  .chart-container {
    min-height: 300px; /* Ensure minimum height on mobile */
    padding: 8px !important;
  }
}

/* Legend styling */
.legend-container {
  background-color: rgba(0, 0, 0, 0.04);
  padding: 6px 12px;
  border-radius: 8px;
  gap: 12px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  background-color: rgba(255, 255, 255, 0.5);
  border-radius: 12px;
}

.legend-circle {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  display: inline-block;
  border: 2px solid rgba(0, 0, 0, 0.1);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

/* Legend circle colors are now applied via inline styles for colorblind mode support */

.legend-text {
  font-size: 0.75rem;
  font-weight: 500;
  white-space: nowrap;
}

.gap-2 {
  gap: 8px;
}

.gap-3 {
  gap: 12px;
}

/* Map instruction text */
.map-instruction {
  font-size: 0.95rem;
  font-weight: 400;
}

/* Selection chip styling */
.selection-chip {
  font-size: 0.875rem !important;
  height: auto !important;
  padding: 4px 8px !important;
}

.selection-chip span {
  font-size: 0.875rem;
}

/* Mobile legend adjustments */
@media (max-width: 600px) {
  .legend-container {
    width: 100%;
    margin-top: 8px;
    padding: 4px 8px;
    gap: 6px;
    overflow-x: auto;
    flex-wrap: nowrap;
  }

  .legend-item {
    padding: 2px 6px;
    flex-shrink: 0;
  }

  .legend-text {
    font-size: 0.65rem;
  }

  .legend-circle {
    width: 12px;
    height: 12px;
  }
}
</style>
