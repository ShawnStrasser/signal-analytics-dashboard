<template>
  <div class="before-after-view">
    <!-- Page Title with Legend -->
    <v-card class="mb-3">
      <v-card-title class="py-2 d-flex align-center flex-wrap">
        <div class="d-flex align-center">
          <v-icon left>mdi-compare</v-icon>
          <span>Before/After Analysis</span>
        </div>
        <v-spacer class="d-none d-sm-flex"></v-spacer>
        <div class="legend-container d-flex align-center flex-wrap mt-2 mt-sm-0">
          <span class="text-caption font-weight-medium mr-2 d-none d-sm-inline">Difference Scale:</span>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendGreenColor }"></div>
            <span class="legend-text"><span class="d-none d-sm-inline">Improved </span>-0.25</span>
          </div>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendYellowColor }"></div>
            <span class="legend-text"><span class="d-none d-sm-inline">Same </span>0</span>
          </div>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendRedColor }"></div>
            <span class="legend-text"><span class="d-none d-sm-inline">Worse </span>+0.25</span>
          </div>
        </div>
      </v-card-title>
    </v-card>

    <!-- Main Content Area (Scrollable) -->
    <div class="content-scrollable">
      <!-- Map Section -->
      <v-card class="map-card mb-3">
        <v-card-title class="py-2 d-flex align-center flex-wrap">
          <div class="d-flex align-center">
            🗺️ Travel Time Change Map
            <span class="map-instruction ml-2 text-medium-emphasis d-none d-md-inline">— Green: Improved, Yellow: Same, Red: Worse</span>
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
            <v-btn size="small" variant="outlined" color="error" @click="clearMapSelections">
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
            data-type="before-after"
            @selection-changed="onSelectionChanged"
          />
          <div v-if="mapIsLoading" class="d-flex justify-center align-center loading-overlay">
            <v-progress-circular indeterminate size="64"></v-progress-circular>
          </div>
          <div v-else-if="!mapIsLoading && mapData.length === 0" class="d-flex justify-center align-center loading-overlay">
            <div class="text-h5 text-grey">NO DATA</div>
          </div>
        </v-card-text>
      </v-card>

      <!-- Main Chart -->
      <v-card class="chart-card mb-3">
        <v-card-title class="py-2 d-flex align-center flex-wrap">
          📈 Before/After Comparison
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
            <v-btn-toggle v-model="aggregateByTimeOfDay" mandatory density="compact" color="primary">
              <v-btn value="false" size="small">By Date/Time</v-btn>
              <v-btn value="true" size="small">By Time of Day</v-btn>
            </v-btn-toggle>
          </div>
        </v-card-title>
        <v-card-subtitle v-if="legendClipped" class="py-1">
          <v-alert density="compact" variant="outlined" color="orange-darken-2" icon="mdi-alert-circle-outline">
            <strong>Maximum legend items reached ({{ maxLegendEntities }})</strong> — Only the first {{ maxLegendEntities }} {{ legendByLabel }} are displayed.
          </v-alert>
        </v-card-subtitle>
        <v-card-text class="chart-container">
          <BeforeAfterChart
            v-if="chartData.length > 0"
            :data="chartData"
            :is-time-of-day="aggregateByTimeOfDay === 'true'"
            :legend-by="legendBy"
          />
          <div v-if="chartIsLoading" class="d-flex justify-center align-center loading-overlay">
            <v-progress-circular indeterminate size="64"></v-progress-circular>
          </div>
          <div v-else-if="!chartIsLoading && chartData.length === 0" class="d-flex justify-center align-center loading-overlay">
            <div class="text-h5 text-grey">NO DATA</div>
          </div>
        </v-card-text>
      </v-card>

      <!-- Small Multiples Chart -->
      <v-card class="chart-card mb-3">
        <v-card-title class="py-2 d-flex align-center flex-wrap">
          📊 Detailed Comparison by Entity
          <v-spacer></v-spacer>
          <div class="d-flex align-center flex-wrap gap-2">
            <v-select
              v-model="smallMultiplesEntity"
              :items="legendOptions"
              label="Group By"
              density="compact"
              variant="outlined"
              hide-details
              style="max-width: 200px;"
            ></v-select>
            <v-btn-toggle v-model="smallMultiplesTimeOfDay" mandatory density="compact" color="primary">
              <v-btn value="false" size="small">By Date/Time</v-btn>
              <v-btn value="true" size="small">By Time of Day</v-btn>
            </v-btn-toggle>
          </div>
        </v-card-title>
        <v-card-subtitle v-if="smallMultiplesClipped" class="py-1">
          <v-alert density="compact" variant="outlined" color="orange-darken-2" icon="mdi-alert-circle-outline">
            <strong>Maximum entities reached ({{ maxLegendEntities }})</strong> — Only the first {{ maxLegendEntities }} {{ smallMultiplesLabel }} are displayed.
          </v-alert>
        </v-card-subtitle>
        <v-card-text class="small-multiples-container">
          <SmallMultiplesChart
            v-if="smallMultiplesData.length > 0 && smallMultiplesEntity !== 'none'"
            :data="smallMultiplesData"
            :is-time-of-day="smallMultiplesTimeOfDay === 'true'"
            :entity-type="smallMultiplesEntity"
          />
          <div v-else-if="smallMultiplesEntity === 'none'" class="d-flex justify-center align-center" style="height: 400px;">
            <div class="text-h6 text-grey">Select a grouping option to view detailed comparison</div>
          </div>
          <div v-else-if="smallMultiplesIsLoading" class="d-flex justify-center align-center loading-overlay">
            <v-progress-circular indeterminate size="64"></v-progress-circular>
          </div>
          <div v-else-if="!smallMultiplesIsLoading && smallMultiplesData.length === 0" class="d-flex justify-center align-center loading-overlay">
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
import { useBeforeAfterFiltersStore } from '@/stores/beforeAfterFilters'
import { useSelectionStore } from '@/stores/selection'
import { useSignalDimensionsStore } from '@/stores/signalDimensions'
import { useXdDimensionsStore } from '@/stores/xdDimensions'
import { useThemeStore } from '@/stores/theme'
import ApiService from '@/services/api'
import SharedMap from '@/components/SharedMap.vue'
import BeforeAfterChart from '@/components/BeforeAfterChart.vue'
import SmallMultiplesChart from '@/components/SmallMultiplesChart.vue'

const filtersStore = useFiltersStore()
const beforeAfterFiltersStore = useBeforeAfterFiltersStore()
const selectionStore = useSelectionStore()
const signalDimensionsStore = useSignalDimensionsStore()
const xdDimensionsStore = useXdDimensionsStore()
const themeStore = useThemeStore()

// Computed legend colors based on colorblind mode
const legendGreenColor = computed(() => themeStore.colorblindMode ? '#0072B2' : '#4caf50')
const legendYellowColor = computed(() => themeStore.colorblindMode ? '#F0E442' : '#ffc107')
const legendRedColor = computed(() => themeStore.colorblindMode ? '#D55E00' : '#d32f2f')

const mapData = ref([])
const xdData = ref([])
const chartData = ref([])
const smallMultiplesData = ref([])
const loadingMap = ref(true)
const loadingChart = ref(true)
const loadingSmallMultiples = ref(true)
const loading = ref(true)
const mapRef = ref(null)
const aggregateByTimeOfDay = ref('false')
const smallMultiplesTimeOfDay = ref('false')
const legendBy = ref('none')
const smallMultiplesEntity = ref('none')
const legendClipped = ref(false)
const smallMultiplesClipped = ref(false)
const maxLegendEntities = ref(10)
const shouldAutoZoomMap = ref(true)

const mapIsLoading = computed(() => loading.value || loadingMap.value)
const chartIsLoading = computed(() => loading.value || loadingChart.value)
const smallMultiplesIsLoading = computed(() => loading.value || loadingSmallMultiples.value)

const legendOptions = [
  { title: 'None', value: 'none' },
  { title: 'XD Segment', value: 'xd' },
  { title: 'Bearing', value: 'bearing' },
  { title: 'County', value: 'county' },
  { title: 'Road Name', value: 'roadname' },
  { title: 'Signal ID', value: 'id' }
]

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

const smallMultiplesLabel = computed(() => {
  const labels = {
    'xd': 'XD segments',
    'bearing': 'bearings',
    'county': 'counties',
    'roadname': 'road names',
    'id': 'signal IDs'
  }
  return labels[smallMultiplesEntity.value] || 'items'
})

// Watch for filter changes
watch(() => [
  beforeAfterFiltersStore.beforeStartDate,
  beforeAfterFiltersStore.beforeEndDate,
  beforeAfterFiltersStore.afterStartDate,
  beforeAfterFiltersStore.afterEndDate,
  filtersStore.selectedSignalIds,
  filtersStore.maintainedBy,
  filtersStore.approach,
  filtersStore.validGeometry,
  filtersStore.startHour,
  filtersStore.startMinute,
  filtersStore.endHour,
  filtersStore.endMinute,
  filtersStore.dayOfWeek,
  filtersStore.removeAnomalies
], async () => {
  if (loading.value) return
  shouldAutoZoomMap.value = true
  loading.value = true
  try {
    if (selectionStore.hasMapSelections) {
      selectionStore.clearAllSelections()
    }
    await Promise.all([loadMapData(), loadChartData(), loadSmallMultiplesData()])
  } finally {
    loading.value = false
  }
}, { deep: true })

watch(aggregateByTimeOfDay, async () => {
  await loadChartData()
})

watch(legendBy, async () => {
  await loadChartData()
})

watch([smallMultiplesEntity, smallMultiplesTimeOfDay], async () => {
  if (smallMultiplesEntity.value !== 'none') {
    await loadSmallMultiplesData()
  }
})

watch(() => [
  selectionStore.selectedSignals.size,
  selectionStore.selectedXdSegments.size,
  selectionStore.allSelectedXdSegments.size
], async () => {
  await Promise.all([loadChartData(), loadSmallMultiplesData()])
})

onMounted(async () => {
  const config = await ApiService.getConfig()
  maxLegendEntities.value = config.maxLegendEntities

  await Promise.all([
    signalDimensionsStore.loadDimensions(),
    xdDimensionsStore.loadDimensions()
  ])

  loading.value = true
  try {
    await Promise.all([loadMapData(), loadChartData()])
  } finally {
    loading.value = false
  }
})

async function loadMapData() {
  try {
    loadingMap.value = true
    const beforeFilters = beforeAfterFiltersStore.beforeFilterParams
    const afterFilters = beforeAfterFiltersStore.afterFilterParams
    const commonFilters = filtersStore.filterParams

    const [signalTable, xdTable] = await Promise.all([
      ApiService.getBeforeAfterSummary(beforeFilters, afterFilters, commonFilters),
      ApiService.getBeforeAfterSummaryXd(beforeFilters, afterFilters, commonFilters)
    ])

    const signalMetrics = ApiService.arrowTableToObjects(signalTable)
    const xdMetrics = ApiService.arrowTableToObjects(xdTable)

    const signalObjects = signalMetrics.map(metric => {
      const dimensions = signalDimensionsStore.getSignalDimensions(metric.ID)
      return {
        ID: metric.ID,
        TTI_BEFORE: metric.TTI_BEFORE,
        TTI_AFTER: metric.TTI_AFTER,
        TTI_DIFF: metric.TTI_DIFF,
        NAME: dimensions?.NAME || `Signal ${metric.ID}`,
        LATITUDE: dimensions?.LATITUDE,
        LONGITUDE: dimensions?.LONGITUDE
      }
    }).filter(signal => signal.LATITUDE && signal.LONGITUDE)

    const xdObjects = xdMetrics.map(metric => {
      const dimensions = xdDimensionsStore.getXdDimensions(metric.XD)
      return {
        XD: metric.XD,
        TTI_BEFORE: metric.TTI_BEFORE,
        TTI_AFTER: metric.TTI_AFTER,
        TTI_DIFF: metric.TTI_DIFF,
        ID: dimensions?.ID,
        BEARING: dimensions?.BEARING,
        ROADNAME: dimensions?.ROADNAME,
        MILES: dimensions?.MILES,
        APPROACH: dimensions?.APPROACH
      }
    })

    console.log('🔍 Before/After Map Data Sample:', {
      signalCount: signalObjects.length,
      xdCount: xdObjects.length,
      sampleSignal: signalObjects[0],
      sampleXd: xdObjects[0],
      signalsSample: signalObjects.slice(0, 3),
      xdSample: xdObjects.slice(0, 3)
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
    const beforeFilters = beforeAfterFiltersStore.beforeFilterParams
    const afterFilters = beforeAfterFiltersStore.afterFilterParams
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
      arrowTable = await ApiService.getBeforeAfterByTimeOfDay(beforeFilters, afterFilters, filters, legendBy.value)
    } else {
      arrowTable = await ApiService.getBeforeAfterAggregated(beforeFilters, afterFilters, filters, legendBy.value)
    }

    const data = ApiService.arrowTableToObjects(arrowTable)

    if (data.length > 0 && data[0].LEGEND_GROUP !== undefined) {
      const uniqueGroups = new Set(data.map(row => row.LEGEND_GROUP))
      legendClipped.value = uniqueGroups.size === maxLegendEntities.value
    } else {
      legendClipped.value = false
    }

    chartData.value = data
  } catch (error) {
    console.error('Failed to load chart data:', error)
    chartData.value = []
  } finally {
    loadingChart.value = false
  }
}

async function loadSmallMultiplesData() {
  if (smallMultiplesEntity.value === 'none') {
    smallMultiplesData.value = []
    return
  }

  try {
    loadingSmallMultiples.value = true
    const beforeFilters = beforeAfterFiltersStore.beforeFilterParams
    const afterFilters = beforeAfterFiltersStore.afterFilterParams
    const filters = { ...filtersStore.filterParams }

    if (selectionStore.hasMapSelections) {
      const selectedXds = Array.from(selectionStore.allSelectedXdSegments)
      if (selectedXds.length > 0) {
        filters.xd_segments = selectedXds
      } else {
        smallMultiplesData.value = []
        return
      }
    }

    let arrowTable
    if (smallMultiplesTimeOfDay.value === 'true') {
      arrowTable = await ApiService.getBeforeAfterByTimeOfDay(beforeFilters, afterFilters, filters, smallMultiplesEntity.value)
    } else {
      arrowTable = await ApiService.getBeforeAfterAggregated(beforeFilters, afterFilters, filters, smallMultiplesEntity.value)
    }

    const data = ApiService.arrowTableToObjects(arrowTable)

    if (data.length > 0 && data[0].LEGEND_GROUP !== undefined) {
      const uniqueGroups = new Set(data.map(row => row.LEGEND_GROUP))
      smallMultiplesClipped.value = uniqueGroups.size === maxLegendEntities.value
    } else {
      smallMultiplesClipped.value = false
    }

    smallMultiplesData.value = data
  } catch (error) {
    console.error('Failed to load small multiples data:', error)
    smallMultiplesData.value = []
  } finally {
    loadingSmallMultiples.value = false
  }
}

function onSelectionChanged() {
  // Selection changed via map interaction
}

function clearMapSelections() {
  selectionStore.clearAllSelections()
}
</script>

<style scoped>
.before-after-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.content-scrollable {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 20px;
}

.map-card,
.chart-card {
  display: flex;
  flex-direction: column;
}

.map-container {
  height: 500px;
  position: relative;
  padding: 12px !important;
}

.chart-container {
  height: 400px;
  position: relative;
  padding: 12px !important;
}

.small-multiples-container {
  height: 600px;
  position: relative;
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

.map-instruction {
  font-size: 0.95rem;
  font-weight: 400;
}

.selection-chip {
  font-size: 0.875rem !important;
  height: auto !important;
  padding: 4px 8px !important;
}

@media (max-width: 960px) {
  .map-container {
    height: 400px;
  }

  .chart-container {
    height: 350px;
  }

  .small-multiples-container {
    height: 500px;
  }
}
</style>
