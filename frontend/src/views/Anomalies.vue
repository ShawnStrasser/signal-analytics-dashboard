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
          </v-card-title>
          <v-card-subtitle>
            Bubble size represents number of {{ filtersStore.anomalyType.toLowerCase() }} anomalies
          </v-card-subtitle>
          <v-card-text>
            <div style="height: 500px; position: relative;">
              <SharedMap
                v-if="mapData.length > 0"
                :signals="mapData"
                data-type="anomaly"
                :anomaly-type="filtersStore.anomalyType"
                @signal-selected="onSignalSelected"
              />
              <div v-else class="d-flex justify-center align-center" style="height: 100%;">
                <v-progress-circular indeterminate size="64"></v-progress-circular>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Signal Selection -->
    <v-row v-if="filtersStore.selectedSignalFromMap" class="mt-2">
      <v-col cols="12">
        <v-card color="success" variant="tonal">
          <v-card-text>
            <div class="d-flex justify-space-between align-center">
              <div>
                ✅ Selected Signal: {{ filtersStore.selectedSignalFromMap }}
              </div>
              <v-btn 
                size="small" 
                variant="outlined" 
                @click="filtersStore.clearSelectedSignalFromMap()"
              >
                Clear Selection
              </v-btn>
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
                :selected-signal="filtersStore.selectedSignalFromMap"
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
import ApiService from '@/services/api'
import SharedMap from '@/components/SharedMap.vue'
import AnomalyChart from '@/components/AnomalyChart.vue'

const filtersStore = useFiltersStore()
const mapData = ref([])
const chartData = ref([])
const detailedData = ref([])
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

// Watch for filter changes
watch(() => filtersStore.filterParams, async () => {
  await loadMapData()
  await loadChartData()
  await loadDetailedData()
}, { deep: true })

// Watch for signal selection changes
watch(() => filtersStore.selectedSignalFromMap, async () => {
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
    loadingMap.value = true
    const arrowTable = await ApiService.getAnomalySummary(filtersStore.filterParams)
    mapData.value = ApiService.arrowTableToObjects(arrowTable)
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
    
    const filters = { ...filtersStore.filterParams }
    if (filtersStore.selectedSignalFromMap) {
      filters.signal_ids = [filtersStore.selectedSignalFromMap]
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
    
    const filters = { ...filtersStore.filterParams }
    if (filtersStore.selectedSignalFromMap) {
      filters.signal_ids = [filtersStore.selectedSignalFromMap]
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

function onSignalSelected(signalId) {
  filtersStore.setSelectedSignalFromMap(signalId)
}
</script>