<template>
  <div class="travel-time-view">
    <!-- Page Title -->
    <v-card class="mb-3">
      <v-card-title class="py-2">
        <v-icon left>mdi-chart-line</v-icon>
        Travel Time Index Analysis
      </v-card-title>
    </v-card>

    <!-- Selection Summary -->
    <v-card v-if="selectionStore.hasMapSelections" color="info" variant="tonal" class="mb-3">
      <v-card-text class="py-2">
        <div>
          <strong>Map Selection:</strong>
          <span v-if="selectionStore.selectedSignals.size > 0">
            {{ selectionStore.selectedSignals.size }} signal(s) selected
          </span>
          <span v-if="selectionStore.selectedSignals.size > 0 && selectionStore.selectedXdSegments.size > 0"> • </span>
          <span v-if="selectionStore.selectedXdSegments.size > 0">
            {{ selectionStore.selectedXdSegments.size }} XD segment(s) directly selected
          </span>
        </div>
        <div class="text-caption mt-1">
          Chart below is filtered to {{ selectionStore.allSelectedXdSegments.size }} total XD segment(s)
        </div>
      </v-card-text>
    </v-card>

    <!-- Main Content Area with Dynamic Height -->
    <div class="content-grid">
      <!-- Map Section -->
      <v-card class="map-card">
        <v-card-title class="py-2 d-flex align-center">
          🗺️ Traffic Signals Map
          <v-spacer></v-spacer>
          <v-btn
            v-if="selectionStore.hasMapSelections"
            size="small"
            variant="outlined"
            color="error"
            @click="clearMapSelections"
          >
            Clear Map Selections
          </v-btn>
        </v-card-title>
        <v-card-subtitle class="py-1">
          Signal points show travel time index by color. Click signals or XD segments to filter the chart below.
        </v-card-subtitle>
        <v-card-text class="map-container">
          <SharedMap
            ref="mapRef"
            v-if="mapData.length > 0"
            :signals="mapData"
            data-type="travel-time"
            @selection-changed="onSelectionChanged"
          />
          <div v-if="loading" class="d-flex justify-center align-center loading-overlay">
            <v-progress-circular indeterminate size="64"></v-progress-circular>
          </div>
          <div v-else-if="!loading && mapData.length === 0" class="d-flex justify-center align-center loading-overlay">
            <div class="text-h5 text-grey">NO DATA</div>
          </div>
        </v-card-text>
      </v-card>

      <!-- Time Series Chart -->
      <v-card class="chart-card">
        <v-card-title class="py-2 d-flex align-center flex-wrap">
          📈 Travel Time Index Time Series
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
          <div v-if="loading" class="d-flex justify-center align-center loading-overlay">
            <v-progress-circular indeterminate size="64"></v-progress-circular>
          </div>
          <div v-else-if="!loading && chartData.length === 0" class="d-flex justify-center align-center loading-overlay">
            <div class="text-h5 text-grey">NO DATA</div>
          </div>
        </v-card-text>
      </v-card>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { useFiltersStore } from '@/stores/filters'
import { useSelectionStore } from '@/stores/selection'
import { useMapDataCacheStore } from '@/stores/mapDataCache'
import ApiService from '@/services/api'
import SharedMap from '@/components/SharedMap.vue'
import TravelTimeChart from '@/components/TravelTimeChart.vue'

const filtersStore = useFiltersStore()
const selectionStore = useSelectionStore()
const mapDataCacheStore = useMapDataCacheStore()
const mapData = ref([])
const chartData = ref([])
const loadingMap = ref(false)
const loadingChart = ref(false)
const loading = ref(false) // Global loading state
const mapRef = ref(null)
const aggregateByTimeOfDay = ref('false') // Toggle for time-of-day aggregation
const legendBy = ref('none') // Legend grouping selection
const legendClipped = ref(false) // Whether legend entities were clipped
const maxLegendEntities = ref(10) // Max legend entities from backend config

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

// Watch for geometry/signal filter changes (triggers auto-zoom)
watch(() => [
  filtersStore.selectedSignalIds,
  filtersStore.maintainedBy,
  filtersStore.approach,
  filtersStore.validGeometry
], async () => {
  if (loading.value) {
    console.log('⏸️ Already loading - skipping filter change')
    return
  }

  console.log('🔄 Geometry filters changed - reloading with auto-zoom')
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
}, { deep: true })

// Watch for time-of-day aggregation toggle
watch(aggregateByTimeOfDay, async () => {
  console.log('🕐 Time-of-day aggregation toggled - reloading chart data')
  await loadChartData()
})

// Watch for legend selection changes
watch(legendBy, async () => {
  console.log('🏷️ Legend selection changed - reloading chart data')
  await loadChartData()
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

onMounted(async () => {
  const t0 = performance.now()
  console.log('🚀 TravelTime.vue: onMounted START')

  // Fetch config first
  const config = await ApiService.getConfig()
  maxLegendEntities.value = config.maxLegendEntities

  // Load map and chart data in parallel
  await Promise.all([
    loadMapData(),
    loadChartData()
  ])

  const t1 = performance.now()
  console.log(`✅ TravelTime.vue: onMounted COMPLETE, total ${(t1 - t0).toFixed(2)}ms`)
})

async function loadMapData() {
  try {
    console.log('📡 API: Loading map data START', filtersStore.filterParams)
    const t0 = performance.now()
    loadingMap.value = true

    // Check if this is an "all signals" query (no filters applied)
    const isAllSignals = (!filtersStore.selectedSignalIds || filtersStore.selectedSignalIds.length === 0) &&
                         filtersStore.maintainedBy === 'all' &&
                         !filtersStore.approach &&
                         (!filtersStore.validGeometry || filtersStore.validGeometry === 'all')

    // Try cache first for "all signals" queries
    if (isAllSignals) {
      const cached = mapDataCacheStore.getTravelTimeCache(
        filtersStore.startDate,
        filtersStore.endDate,
        filtersStore.startHour,
        filtersStore.startMinute,
        filtersStore.endHour,
        filtersStore.endMinute,
        filtersStore.dayOfWeek
      )

      if (cached) {
        mapData.value = cached
        const t1 = performance.now()
        console.log(`📡 API: Loading map data DONE (CACHED) - ${mapData.value.length} records in ${(t1 - t0).toFixed(2)}ms`)
        return
      }
    }

    // Cache miss or filtered query - fetch from backend
    const arrowTable = await ApiService.getTravelTimeSummary(filtersStore.filterParams)
    const t1 = performance.now()
    console.log(`📡 API: getTravelTimeSummary took ${(t1 - t0).toFixed(2)}ms`)

    const conversionStart = performance.now()
    const objects = ApiService.arrowTableToObjects(arrowTable)
    const t2 = performance.now()
    console.log(`📡 API: arrowTableToObjects took ${(t2 - conversionStart).toFixed(2)}ms`)

    // Cache "all signals" result
    if (isAllSignals) {
      mapDataCacheStore.setTravelTimeCache(
        filtersStore.startDate,
        filtersStore.endDate,
        filtersStore.startHour,
        filtersStore.startMinute,
        filtersStore.endHour,
        filtersStore.endMinute,
        filtersStore.dayOfWeek,
        objects
      )
    }

    const assignmentStart = performance.now()
    mapData.value = objects
    const t3 = performance.now()
    console.log(`📡 API: mapData assignment took ${(t3 - assignmentStart).toFixed(2)}ms`)
    console.log(`📡 API: Loading map data DONE - ${mapData.value.length} records in ${(t3 - t0).toFixed(2)}ms`)

    // Log time from assignment to end of function
    const t4 = performance.now()
    console.log(`📡 API: Post-assignment overhead ${(t4 - t3).toFixed(2)}ms`)
  } catch (error) {
    console.error('Failed to load map data:', error)
    mapData.value = []
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

    // Use different API based on aggregation type
    let arrowTable
    let t1
    if (aggregateByTimeOfDay.value === 'true') {
      arrowTable = await ApiService.getTravelTimeByTimeOfDay(filters, legendBy.value)
      t1 = performance.now()
      console.log(`📊 API: getTravelTimeByTimeOfDay took ${(t1 - t0).toFixed(2)}ms`)
    } else {
      arrowTable = await ApiService.getTravelTimeAggregated(filters, legendBy.value)
      t1 = performance.now()
      console.log(`📊 API: getTravelTimeAggregated took ${(t1 - t0).toFixed(2)}ms`)
    }

    const data = ApiService.arrowTableToObjects(arrowTable)

    // Check if data contains LEGEND_GROUP column (indicates legend grouping is active)
    if (data.length > 0 && data[0].LEGEND_GROUP !== undefined) {
      // Count unique legend groups to detect if we hit the MAX_LEGEND_ENTITIES limit
      const uniqueGroups = new Set(data.map(row => row.LEGEND_GROUP))
      // Show warning when we have exactly maxLegendEntities groups (the backend limit from config.py)
      legendClipped.value = uniqueGroups.size === maxLegendEntities.value
    } else {
      legendClipped.value = false
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
</style>