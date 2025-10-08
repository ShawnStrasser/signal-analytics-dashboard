<template>
  <div class="anomalies-view">
    <!-- Page Title -->
    <v-card class="mb-3">
      <v-card-title class="py-2">
        <v-icon left>mdi-alert</v-icon>
        Anomaly Analysis
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
          Chart and table below are filtered to {{ selectionStore.allSelectedXdSegments.size }} total XD segment(s)
        </div>
      </v-card-text>
    </v-card>

    <!-- Main Content Area with Dynamic Height -->
    <div class="content-grid">
      <!-- Map Section -->
      <v-card class="map-card">
        <v-card-title class="py-2 d-flex align-center">
          🗺️ Anomaly Distribution Map
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
          Signal points show {{ filtersStore.anomalyType.toLowerCase() }} anomaly count by color. Click signals or XD segments to filter the chart and table below.
        </v-card-subtitle>
        <v-card-text class="map-container">
          <SharedMap
            ref="mapRef"
            v-if="mapData.length > 0"
            :signals="mapData"
            data-type="anomaly"
            :anomaly-type="filtersStore.anomalyType"
            @selection-changed="onSelectionChanged"
          />
          <div v-if="loading || mapData.length === 0" class="d-flex justify-center align-center loading-overlay">
            <v-progress-circular indeterminate size="64"></v-progress-circular>
          </div>
        </v-card-text>
      </v-card>

      <!-- Chart Section -->
      <v-card class="chart-card">
        <v-card-title class="py-2">
          📈 Travel Time Analysis with Anomaly Detection
        </v-card-title>
        <v-card-text class="chart-container">
          <AnomalyChart
            v-if="chartData.length > 0"
            :data="chartData"
          />
          <div v-if="loading || chartData.length === 0" class="d-flex justify-center align-center loading-overlay">
            <v-progress-circular indeterminate size="64"></v-progress-circular>
          </div>
        </v-card-text>
      </v-card>

      <!-- Anomaly Details Table -->
      <v-card v-if="anomaliesTableData.length > 0" class="table-card">
        <v-card-title class="py-2">
          📋 Anomaly Details
        </v-card-title>
        <v-card-text class="table-container">
          <v-data-table
            :headers="tableHeaders"
            :items="anomaliesTableData"
            :items-per-page="10"
            density="compact"
            class="elevation-1"
          >
            <template v-slot:item.ORIGINATED_ANOMALY="{ item }">
              <v-chip
                :color="item.ORIGINATED_ANOMALY ? 'error' : 'default'"
                size="small"
              >
                {{ item.ORIGINATED_ANOMALY ? 'Yes' : 'No' }}
              </v-chip>
            </template>
          </v-data-table>
        </v-card-text>
      </v-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useFiltersStore } from '@/stores/filters'
import { useSelectionStore } from '@/stores/selection'
import { useMapDataCacheStore } from '@/stores/mapDataCache'
import ApiService from '@/services/api'
import SharedMap from '@/components/SharedMap.vue'
import AnomalyChart from '@/components/AnomalyChart.vue'

const filtersStore = useFiltersStore()
const selectionStore = useSelectionStore()
const mapDataCacheStore = useMapDataCacheStore()
const mapData = ref([])
const chartData = ref([])
const detailedData = ref([])
const mapRef = ref(null)
const loadingMap = ref(false)
const loadingChart = ref(false)
const loadingDetails = ref(false)
const loading = ref(false) // Global loading state

const tableHeaders = [
  { title: 'Timestamp', key: 'TIMESTAMP', sortable: true },
  { title: 'Signal ID', key: 'ID', sortable: true },
  { title: 'Actual (sec)', key: 'TRAVEL_TIME_SECONDS', sortable: true },
  { title: 'Predicted (sec)', key: 'PREDICTION', sortable: true },
  { title: 'Point Source', key: 'ORIGINATED_ANOMALY', sortable: true },
]

// Filter anomalies for table display
const anomaliesTableData = computed(() => {
  return detailedData.value
    .filter(item => item.ANOMALY === true || item.ANOMALY === 1)
    .map(item => ({
      ...item,
      TIMESTAMP: new Date(item.TIMESTAMP).toLocaleString(),
      TRAVEL_TIME_SECONDS: item.TRAVEL_TIME_SECONDS?.toFixed(1) || 'N/A',
      PREDICTION: item.PREDICTION?.toFixed(1) || 'N/A',
    }))
    .slice(0, 100) // Limit to first 100 for performance
})

// Watch for geometry/signal/anomaly filter changes (triggers auto-zoom)
watch(() => [
  filtersStore.selectedSignalIds,
  filtersStore.approach,
  filtersStore.validGeometry,
  filtersStore.anomalyType
], async () => {
  if (loading.value) {
    console.log('⏸️ Already loading - skipping filter change')
    return
  }

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
      loadChartData(),
      loadDetailedData()
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
      loadChartData(),
      loadDetailedData()
    ])
  } finally {
    loading.value = false
  }
})

// Watch for selection changes - reload chart and detail data in parallel
// Watch the Set sizes and allSelectedXdSegments size to detect changes
watch(() => [
  selectionStore.selectedSignals.size,
  selectionStore.selectedXdSegments.size,
  selectionStore.allSelectedXdSegments.size
], async () => {
  console.log('Selection changed - reloading chart and detail data')
  await Promise.all([
    loadChartData(),
    loadDetailedData()
  ])
})

onMounted(async () => {
  const t0 = performance.now()
  console.log('🚀 Anomalies.vue: onMounted START')

  // Load all data in parallel
  await Promise.all([
    loadMapData(),
    loadChartData(),
    loadDetailedData()
  ])

  const t1 = performance.now()
  console.log(`✅ Anomalies.vue: onMounted COMPLETE, total ${(t1 - t0).toFixed(2)}ms`)
})

async function loadMapData() {
  try {
    const t0 = performance.now()
    loadingMap.value = true

    // Check if this is an "all signals" query (no signal filter)
    const isAllSignals = !filtersStore.selectedSignalIds || filtersStore.selectedSignalIds.length === 0

    // Try cache first for "all signals" queries
    if (isAllSignals) {
      const cached = mapDataCacheStore.getAnomalyCache(
        filtersStore.startDate,
        filtersStore.endDate,
        filtersStore.anomalyType,
        filtersStore.startHour,
        filtersStore.startMinute,
        filtersStore.endHour,
        filtersStore.endMinute,
        filtersStore.dayOfWeek
      )

      if (cached) {
        mapData.value = cached
        const t1 = performance.now()
        console.log(`📡 API: Loading anomaly map data DONE (CACHED) - ${mapData.value.length} records in ${(t1 - t0).toFixed(2)}ms`)
        return
      }
    }

    // Cache miss or filtered query - fetch from backend
    const arrowTable = await ApiService.getAnomalySummary(filtersStore.filterParams)
    const objects = ApiService.arrowTableToObjects(arrowTable)

    // Cache "all signals" result
    if (isAllSignals) {
      mapDataCacheStore.setAnomalyCache(
        filtersStore.startDate,
        filtersStore.endDate,
        filtersStore.anomalyType,
        filtersStore.startHour,
        filtersStore.startMinute,
        filtersStore.endHour,
        filtersStore.endMinute,
        filtersStore.dayOfWeek,
        objects
      )
    }

    mapData.value = objects
    const t1 = performance.now()
    console.log(`📡 API: Loading anomaly map data DONE - ${mapData.value.length} records in ${(t1 - t0).toFixed(2)}ms`)
  } catch (error) {
    console.error('Failed to load anomaly map data:', error)
    mapData.value = []
  } finally {
    loadingMap.value = false
  }
}

async function loadChartData() {
  try {
    loadingChart.value = true
    
    // Build filter params for chart based on selections
    const filters = { ...filtersStore.filterParams }
    
    // If there are map selections, send the selected XD segments directly
    if (selectionStore.hasMapSelections) {
      const selectedXds = Array.from(selectionStore.allSelectedXdSegments)
      
      if (selectedXds.length > 0) {
        filters.xd_segments = selectedXds
      } else {
        // No selections, show empty chart
        chartData.value = []
        return
      }
    }
    
    const arrowTable = await ApiService.getAnomalyAggregated(filters)
    chartData.value = ApiService.arrowTableToObjects(arrowTable)
  } catch (error) {
    console.error('Failed to load anomaly chart data:', error)
    chartData.value = []
  } finally {
    loadingChart.value = false
  }
}

async function loadDetailedData() {
  try {
    loadingDetails.value = true
    
    // Build filter params for table based on selections
    const filters = { ...filtersStore.filterParams }
    
    // If there are map selections, send the selected XD segments directly
    if (selectionStore.hasMapSelections) {
      const selectedXds = Array.from(selectionStore.allSelectedXdSegments)
      
      if (selectedXds.length > 0) {
        filters.xd_segments = selectedXds
      } else {
        // No selections, show empty table
        detailedData.value = []
        return
      }
    }
    
    const arrowTable = await ApiService.getTravelTimeData(filters)
    detailedData.value = ApiService.arrowTableToObjects(arrowTable)
  } catch (error) {
    console.error('Failed to load detailed anomaly data:', error)
    detailedData.value = []
  } finally {
    loadingDetails.value = false
  }
}

function onSelectionChanged() {
  // Selection changed via map interaction - chart and table will auto-update via watchers
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
  grid-template-rows: 1fr 1fr auto;
  gap: 12px;
  flex: 1;
  min-height: 0; /* Critical for grid to respect parent height */
}

.map-card,
.chart-card,
.table-card {
  display: flex;
  flex-direction: column;
  min-height: 0; /* Allow cards to shrink */
  overflow: hidden;
}

.table-card {
  min-height: auto; /* Table can be auto-sized */
  max-height: 500px; /* Limit table height */
}

.map-container,
.chart-container {
  flex: 1;
  position: relative;
  min-height: 0; /* Allow containers to shrink */
  padding: 12px !important;
}

.table-container {
  padding: 12px !important;
  overflow: auto;
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
    grid-template-rows: auto auto auto;
    gap: 8px;
  }

  .map-container,
  .chart-container {
    min-height: 300px; /* Ensure minimum height on mobile */
    padding: 8px !important;
  }

  .table-card {
    max-height: 400px;
  }
}
</style>