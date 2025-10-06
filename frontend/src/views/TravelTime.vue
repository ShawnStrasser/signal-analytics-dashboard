<template>
  <div>
    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title>
            <v-icon left>mdi-chart-line</v-icon>
            Travel Time Index Analysis
          </v-card-title>
        </v-card>
      </v-col>
    </v-row>

    <!-- Map Section -->
    <v-row class="mt-4">
      <v-col cols="12">
        <v-card>
          <v-card-title>
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
          <v-card-subtitle>
            Signal points show travel time index by color. Click signals or XD segments to filter the chart below.
          </v-card-subtitle>
          <v-card-text>
            <div style="height: 500px; position: relative;">
              <SharedMap
                ref="mapRef"
                v-if="mapData.length > 0"
                :signals="mapData"
                data-type="travel-time"
                @selection-changed="onSelectionChanged"
              />
              <div v-if="loading || mapData.length === 0" class="d-flex justify-center align-center" style="height: 100%; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(255,255,255,0.8); z-index: 1000;">
                <v-progress-circular indeterminate size="64"></v-progress-circular>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Selection Summary -->
    <v-row v-if="selectionStore.hasMapSelections" class="mt-2">
      <v-col cols="12">
        <v-card color="info" variant="tonal">
          <v-card-text>
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
      </v-col>
    </v-row>

    <!-- Time Series Chart -->
    <v-row class="mt-4">
      <v-col cols="12">
        <v-card>
          <v-card-title>
            📈 Travel Time Index Time Series
          </v-card-title>
          <v-card-text>
            <div style="height: 500px; position: relative;">
              <TravelTimeChart
                v-if="chartData.length > 0"
                :data="chartData"
              />
              <div v-if="loading || chartData.length === 0" class="d-flex justify-center align-center" style="height: 100%; position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(255,255,255,0.8); z-index: 1000;">
                <v-progress-circular indeterminate size="64"></v-progress-circular>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
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

// Watch for geometry/signal filter changes (triggers auto-zoom)
watch(() => [
  filtersStore.selectedSignalIds,
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
  filtersStore.endHour,
  filtersStore.timeFilterEnabled
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

    // Check if this is an "all signals" query (no signal filter)
    const isAllSignals = !filtersStore.selectedSignalIds || filtersStore.selectedSignalIds.length === 0

    // Try cache first for "all signals" queries
    if (isAllSignals) {
      const cached = mapDataCacheStore.getTravelTimeCache(
        filtersStore.startDate,
        filtersStore.endDate
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

    const arrowTable = await ApiService.getTravelTimeAggregated(filters)
    const t1 = performance.now()
    console.log(`📊 API: getTravelTimeAggregated took ${(t1 - t0).toFixed(2)}ms`)

    chartData.value = ApiService.arrowTableToObjects(arrowTable)
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