<template>
  <div class="travel-time-view">
    <!-- Page Title with Legend -->
    <v-card class="mb-3">
      <v-card-title class="py-2 d-flex align-center flex-wrap">
        <div class="d-flex align-center">
          <v-icon left>mdi-chart-line</v-icon>
          <span>Travel Time Index Analysis</span>
        </div>
        <v-spacer class="d-none d-sm-flex"></v-spacer>
        <div class="legend-container d-flex align-center flex-wrap mt-2 mt-sm-0">
          <span class="text-caption font-weight-medium mr-2 d-none d-sm-inline">Legend:</span>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendGreenColor }"></div>
            <span class="legend-text"><span class="d-none d-sm-inline">Low </span>1</span>
          </div>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendYellowColor }"></div>
            <span class="legend-text"><span class="d-none d-sm-inline">Med </span>2</span>
          </div>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendRedColor }"></div>
            <span class="legend-text"><span class="d-none d-sm-inline">High </span>3</span>
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
            🗺️ Traffic Signals & Road Segments Map
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
            data-type="travel-time"
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

      <!-- Time Series Chart -->
      <v-card class="chart-card">
        <v-card-title class="py-2 d-flex align-center flex-wrap">
          {{ chartHeadingText }}
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
              v-model="aggregateByTimeOfDay"
              mandatory
              density="compact"
              color="primary"
            >
              <v-btn value="false" size="small">
                By Date/Time
              </v-btn>
              <v-btn value="true" size="small">
                By Time of Day
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
          <TravelTimeChart
            v-if="chartData.length > 0"
            :data="chartData"
            :is-time-of-day="aggregateByTimeOfDay === 'true'"
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
import { ref, watch, onMounted, onActivated, onDeactivated, computed } from 'vue'
import { useFiltersStore } from '@/stores/filters'
import { useSelectionStore } from '@/stores/selection'
import { useMapDataCacheStore } from '@/stores/mapDataCache'
import { useSignalDimensionsStore } from '@/stores/signalDimensions'
import { useXdDimensionsStore } from '@/stores/xdDimensions'
import { useThemeStore } from '@/stores/theme'
import ApiService from '@/services/api'
import SharedMap from '@/components/SharedMap.vue'
import TravelTimeChart from '@/components/TravelTimeChart.vue'
import { useDelayedBoolean } from '@/utils/useDelayedBoolean'
import { useMapFilterReloads } from '@/utils/useMapFilterReloads'

const filtersStore = useFiltersStore()
const selectionStore = useSelectionStore()
const mapDataCacheStore = useMapDataCacheStore()
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
const loadingMap = ref(true)
const loadingChart = ref(true)
const loading = ref(true) // Global loading state
const mapRef = ref(null)
const aggregateByTimeOfDay = ref('false') // Toggle for time-of-day aggregation
const legendBy = ref('none') // Legend grouping selection
const legendClipped = ref(false) // Whether legend entities were clipped
const maxLegendEntities = ref(10) // Max legend entities from backend config
const shouldAutoZoomMap = ref(true) // Controls whether the map auto-zooms on data refresh

const aggregationLabelMap = {
  '15min': '15-minute bins',
  'hourly': 'Hourly bins',
  'daily': 'Daily bins'
}

const chartHeadingText = computed(() => {
  if (aggregateByTimeOfDay.value === 'true') {
    return '📈 Travel Time Index - By Time of Day'
  }
  const aggregationLevel = filtersStore.aggregationLevel
  const suffix = aggregationLabelMap[aggregationLevel] || 'Aggregated bins'
  return `📈 Travel Time Index - ${suffix}`
})

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

useMapFilterReloads({
  loggerPrefix: 'TravelTime',
  geometrySources: () => [
    filtersStore.selectedSignalIds,
    filtersStore.maintainedBy,
    filtersStore.approach,
    filtersStore.validGeometry
  ],
  dataSources: () => [
    filtersStore.startDate,
    filtersStore.endDate,
    filtersStore.startHour,
    filtersStore.startMinute,
    filtersStore.endHour,
    filtersStore.endMinute,
    filtersStore.timeFilterEnabled,
    filtersStore.dayOfWeek,
    filtersStore.removeAnomalies
  ],
  shouldAutoZoomRef: shouldAutoZoomMap,
  loadingRef: loading,
  selectionStore,
  reloadOnGeometryChange: async () => {
    await Promise.all([loadMapData(), loadChartData()])
  },
  reloadOnDataChange: async () => {
    await Promise.all([loadMapData(), loadChartData()])
  }
})

// Watch for time-of-day aggregation toggle
watch(aggregateByTimeOfDay, async () => {
  await loadChartData()
})

// Watch for legend selection changes
watch(legendBy, async () => {
  await loadChartData()
})

// Watch for selection changes - reload chart data only
// Watch the Set sizes and allSelectedXdSegments size to detect changes
watch(() => [
  selectionStore.selectedSignals.size,
  selectionStore.selectedXdSegments.size,
  selectionStore.allSelectedXdSegments.size
], async () => {
  await loadChartData()
})

onMounted(async () => {
  // Fetch config first
  const config = await ApiService.getConfig()
  maxLegendEntities.value = config.maxLegendEntities

  // Load dimension data first (once per session)
  // These are cached and won't be re-queried on filter changes
  await Promise.all([
    signalDimensionsStore.loadDimensions(),
    xdDimensionsStore.loadDimensions()
  ])

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
})

onActivated(async () => {
  const currentState = captureSelectionState()

  // Check if selections changed while we were away
  const selectionsChanged = !lastSelectionState.value ||
    currentState.signalsSize !== lastSelectionState.value.signalsSize ||
    currentState.xdSegmentsSize !== lastSelectionState.value.xdSegmentsSize ||
    currentState.signals !== lastSelectionState.value.signals ||
    currentState.xdSegments !== lastSelectionState.value.xdSegments

  if (selectionsChanged) {
    // Set loading state to hide chart during refresh
    loading.value = true
    try {
      await loadChartData()
    } finally {
      loading.value = false
    }
  }
})

onDeactivated(() => {
  // Capture state when leaving the page so we can detect changes on return
  lastSelectionState.value = captureSelectionState()
})

async function loadMapData() {
  try {
    loadingMap.value = true

    const [signalTable, xdTable] = await Promise.all([
      ApiService.getTravelTimeSummary(filtersStore.filterParams),
      ApiService.getTravelTimeSummaryXd(filtersStore.filterParams)
    ])

    const signalMetrics = ApiService.arrowTableToObjects(signalTable)
    const xdMetrics = ApiService.arrowTableToObjects(xdTable)

    const signalObjects = signalMetrics.map(metric => {
      const dimensions = signalDimensionsStore.getSignalDimensions(metric.ID)
      return {
        ID: metric.ID,
        TRAVEL_TIME_INDEX: metric.TRAVEL_TIME_INDEX,
        NAME: dimensions?.NAME || `Signal ${metric.ID}`,
        LATITUDE: dimensions?.LATITUDE,
        LONGITUDE: dimensions?.LONGITUDE
      }
    }).filter(signal => signal.LATITUDE && signal.LONGITUDE)

    const xdObjects = xdMetrics.map(metric => {
      const dimensions = xdDimensionsStore.getXdDimensions(metric.XD)
      const signalIds = dimensions?.signalIds ?? (dimensions?.ID ? [dimensions.ID] : [])
      return {
        XD: metric.XD,
        TRAVEL_TIME_INDEX: metric.TRAVEL_TIME_INDEX,
        ID: dimensions?.ID ?? signalIds[0],
        BEARING: dimensions?.BEARING,
        ROADNAME: dimensions?.ROADNAME,
        MILES: dimensions?.MILES,
        APPROACH: dimensions?.APPROACH,
        signalIds
      }
    })

    mapData.value = signalObjects
    xdData.value = xdObjects
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
    loadingChart.value = true
    const filters = { ...filtersStore.filterParams }

    if (selectionStore.hasMapSelections) {
      const selectedXds = Array.from(selectionStore.allSelectedXdSegments)
      if (selectedXds.length > 0) {
        filters.xd_segments = selectedXds
      } else {
        chartData.value = []
        return
      }
    }

    let arrowTable
    if (aggregateByTimeOfDay.value === 'true') {
      arrowTable = await ApiService.getTravelTimeByTimeOfDay(filters, legendBy.value)
    } else {
      arrowTable = await ApiService.getTravelTimeAggregated(filters, legendBy.value)
    }

    const data = ApiService.arrowTableToObjects(arrowTable)

    if (data.length > 0 && data[0].LEGEND_GROUP !== undefined) {
      const uniqueGroups = new Set(data.map(row => row.LEGEND_GROUP))
      legendClipped.value = uniqueGroups.size === maxLegendEntities.value
    } else {
      legendClipped.value = false
    }

    let filteredData = data
    if (legendBy.value === 'id' && selectionStore.selectedSignals.size > 0 && data.length > 0 && data[0].LEGEND_GROUP !== undefined) {
      const selectedSignalsList = Array.from(selectionStore.selectedSignals)
      const allowedSignals = new Set(selectedSignalsList)
      const selectedXds = Array.from(selectionStore.selectedXdSegments)
      const orphanXds = selectedXds.filter(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        const belongsToSelectedSignal = associatedSignals.some(sigId => selectedSignalsList.includes(sigId))
        return !belongsToSelectedSignal
      })

      orphanXds.forEach(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        associatedSignals.forEach(sigId => allowedSignals.add(sigId))
      })

      filteredData = data.filter(row => {
        const signalId = String(row.LEGEND_GROUP)
        return allowedSignals.has(signalId)
      })
    }

    chartData.value = filteredData
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
.travel-time-view {
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
