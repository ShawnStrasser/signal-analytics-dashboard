<template>
  <div>
    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title>
            <v-icon left>mdi-alert</v-icon>
            Anomaly Analysis
          </v-card-title>
        </v-card>
      </v-col>
    </v-row>

    <!-- Map Section -->
    <v-row class="mt-4">
      <v-col cols="12">
        <v-card>
          <v-card-title>
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
          <v-card-subtitle>
            Signal points show {{ filtersStore.anomalyType.toLowerCase() }} anomaly count by color. Click signals or XD segments to filter the chart and table below.
          </v-card-subtitle>
          <v-card-text>
            <div style="height: 500px; position: relative;">
              <SharedMap
                ref="mapRef"
                v-if="mapData.length > 0"
                :signals="mapData"
                data-type="anomaly"
                :anomaly-type="filtersStore.anomalyType"
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
              Chart and table below are filtered to {{ selectionStore.allSelectedXdSegments.size }} total XD segment(s)
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Dual Chart Section -->
    <v-row class="mt-4">
      <v-col cols="12">
        <v-card>
          <v-card-title>
            📈 Travel Time Analysis with Anomaly Detection
          </v-card-title>
          <v-card-text>
            <div style="height: 500px;">
              <AnomalyChart
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

    <!-- Anomaly Details Table -->
    <v-row class="mt-4" v-if="anomaliesTableData.length > 0">
      <v-col cols="12">
        <v-card>
          <v-card-title>
            📋 Anomaly Details
          </v-card-title>
          <v-card-text>
            <v-data-table
              :headers="tableHeaders"
              :items="anomaliesTableData"
              :items-per-page="10"
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
      </v-col>
    </v-row>
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

// Watch for filter changes that should reset map selections
// (anything except date range changes)
watch(() => [
  filtersStore.selectedSignalIds,
  filtersStore.approach,
  filtersStore.validGeometry,
  filtersStore.anomalyType
], () => {
  // Reset map selections when these filters change
  if (selectionStore.hasMapSelections) {
    selectionStore.clearAllSelections()
  }
  
  // Rezoom map to fit the new filtered signals after data loads
  // Wait a bit for the map to update with new markers
  setTimeout(() => {
    if (mapRef.value) {
      mapRef.value.rezoomToSignals()
    }
  }, 100)
})

// Watch for filter changes - reload all data
watch(() => filtersStore.filterParams, async () => {
  await loadMapData()
  await loadChartData()
  await loadDetailedData()
}, { deep: true })

// Watch for selection changes - reload chart and detail data only
// Watch the Set sizes and allSelectedXdSegments size to detect changes
watch(() => [
  selectionStore.selectedSignals.size,
  selectionStore.selectedXdSegments.size,
  selectionStore.allSelectedXdSegments.size
], async () => {
  console.log('Selection changed - reloading chart and detail data')
  await loadChartData()
  await loadDetailedData()
})

onMounted(async () => {
  await loadMapData()
  await loadChartData()
  await loadDetailedData()
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
        filtersStore.anomalyType
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