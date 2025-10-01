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
              <div v-else class="d-flex justify-center align-center" style="height: 100%;">
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
            <div style="height: 500px;">
              <TravelTimeChart
                v-if="chartData.length > 0"
                :data="chartData"
              />
              <div v-else class="d-flex justify-center align-center" style="height: 100%;">
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
import ApiService from '@/services/api'
import SharedMap from '@/components/SharedMap.vue'
import TravelTimeChart from '@/components/TravelTimeChart.vue'

const filtersStore = useFiltersStore()
const selectionStore = useSelectionStore()
const mapData = ref([])
const chartData = ref([])
const loadingMap = ref(false)
const loadingChart = ref(false)
const mapRef = ref(null)

// Watch for filter changes that should reset map selections
// (anything except date range changes)
watch(() => [
  filtersStore.selectedSignalIds,
  filtersStore.approach,
  filtersStore.validGeometry
], () => {
  // Reset map selections when these filters change
  if (selectionStore.hasMapSelections) {
    selectionStore.clearAllSelections()
  }
  // Note: Map will auto-zoom via autoZoomToSignals when new data loads
})

// Watch for any filter changes - reload map data
watch(() => filtersStore.filterParams, async () => {
  await loadMapData()
  await loadChartData()
}, { deep: true })

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
  await loadMapData()
  await loadChartData()
})

async function loadMapData() {
  try {
    console.log('📡 API: Loading map data START', filtersStore.filterParams)
    const t0 = performance.now()
    loadingMap.value = true

    const arrowTable = await ApiService.getTravelTimeSummary(filtersStore.filterParams)
    const t1 = performance.now()
    console.log(`📡 API: getTravelTimeSummary took ${(t1 - t0).toFixed(2)}ms`)

    mapData.value = ApiService.arrowTableToObjects(arrowTable)
    const t2 = performance.now()
    console.log(`📡 API: arrowTableToObjects took ${(t2 - t1).toFixed(2)}ms`)
    console.log(`📡 API: Loading map data DONE - ${mapData.value.length} records in ${(t2 - t0).toFixed(2)}ms`)
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