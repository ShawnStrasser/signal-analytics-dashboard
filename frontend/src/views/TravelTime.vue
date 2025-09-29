<template>
  <div>
    <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title>
            <v-icon left>mdi-chart-line</v-icon>
            Travel Time Analysis
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
          </v-card-title>
          <v-card-subtitle>
            Bubble size represents total travel time, color represents average travel time
          </v-card-subtitle>
          <v-card-text>
            <div style="height: 500px; position: relative;">
              <SharedMap
                v-if="mapData.length > 0"
                :signals="mapData"
                data-type="travel-time"
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
                ✅ Analyzing Signal: {{ filtersStore.selectedSignalFromMap }}
              </div>
              <v-btn 
                size="small" 
                variant="outlined" 
                @click="filtersStore.clearSelectedSignalFromMap()"
              >
                Clear Selection
              </v-btn>
            </div>
            
            <!-- Signal Stats -->
            <v-row class="mt-2" v-if="selectedSignalStats">
              <v-col cols="4">
                <v-card variant="outlined">
                  <v-card-text>
                    <div class="text-h6">{{ selectedSignalStats.TOTAL_TRAVEL_TIME?.toFixed(0) }}s</div>
                    <div class="text-caption">Total Travel Time</div>
                  </v-card-text>
                </v-card>
              </v-col>
              <v-col cols="4">
                <v-card variant="outlined">
                  <v-card-text>
                    <div class="text-h6">{{ selectedSignalStats.AVG_TRAVEL_TIME?.toFixed(1) }}s</div>
                    <div class="text-caption">Average Travel Time</div>
                  </v-card-text>
                </v-card>
              </v-col>
              <v-col cols="4">
                <v-card variant="outlined">
                  <v-card-text>
                    <div class="text-h6">{{ selectedSignalStats.RECORD_COUNT }}</div>
                    <div class="text-caption">Records</div>
                  </v-card-text>
                </v-card>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Time Series Chart -->
    <v-row class="mt-4">
      <v-col cols="12">
        <v-card>
          <v-card-title>
            📈 Travel Time Time Series
          </v-card-title>
          <v-card-text>
            <div style="height: 500px;">
              <TravelTimeChart
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
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useFiltersStore } from '@/stores/filters'
import ApiService from '@/services/api'
import SharedMap from '@/components/SharedMap.vue'
import TravelTimeChart from '@/components/TravelTimeChart.vue'

const filtersStore = useFiltersStore()
const mapData = ref([])
const chartData = ref([])
const loadingMap = ref(false)
const loadingChart = ref(false)

// Computed property for selected signal stats
const selectedSignalStats = computed(() => {
  if (!filtersStore.selectedSignalFromMap) return null
  return mapData.value.find(signal => signal.ID === filtersStore.selectedSignalFromMap)
})

// Watch for filter changes
watch(() => filtersStore.filterParams, async () => {
  await loadMapData()
  await loadChartData()
}, { deep: true })

onMounted(async () => {
  await loadMapData()
  await loadChartData()
})

async function loadMapData() {
  try {
    loadingMap.value = true
    const arrowTable = await ApiService.getTravelTimeSummary(filtersStore.filterParams)
    mapData.value = ApiService.arrowTableToObjects(arrowTable)
  } catch (error) {
    console.error('Failed to load map data:', error)
    mapData.value = []
  } finally {
    loadingMap.value = false
  }
}

async function loadChartData() {
  try {
    loadingChart.value = true
    
    // Get chart data based on selection
    const filters = { ...filtersStore.filterParams }
    if (filtersStore.selectedSignalFromMap) {
      filters.signal_ids = [filtersStore.selectedSignalFromMap]
    }
    
    const arrowTable = await ApiService.getTravelTimeAggregated(filters)
    chartData.value = ApiService.arrowTableToObjects(arrowTable)
  } catch (error) {
    console.error('Failed to load chart data:', error)
    chartData.value = []
  } finally {
    loadingChart.value = false
  }
}

function onSignalSelected(signalId) {
  filtersStore.setSelectedSignalFromMap(signalId)
  loadChartData() // Reload chart data for selected signal
}
</script>