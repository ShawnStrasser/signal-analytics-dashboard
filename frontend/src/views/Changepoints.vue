<template>
  <div class="changepoints-view">
    <v-card class="mb-3">
      <v-card-title class="py-2 d-flex align-center flex-wrap">
        <div class="d-flex align-center">
          <v-icon left>mdi-chart-bell-curve-cumulative</v-icon>
          <span>Changepoint Analysis</span>
        </div>
        <v-spacer class="d-none d-sm-flex"></v-spacer>
        <div class="legend-container d-flex align-center flex-wrap mt-2 mt-sm-0">
          <span class="text-caption font-weight-medium mr-2 d-none d-sm-inline">Legend:</span>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendBetterColor }"></div>
            <span class="legend-text">Decrease -5%</span>
          </div>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendNeutralColor }"></div>
            <span class="legend-text">No Change 0%</span>
          </div>
          <div class="legend-item">
            <div class="legend-circle" :style="{ backgroundColor: legendWorseColor }"></div>
            <span class="legend-text">Increase +5%</span>
          </div>
        </div>
      </v-card-title>
    </v-card>

    <div class="content-grid">
      <v-card class="map-card">
        <v-card-title class="py-2 d-flex align-center flex-wrap">
          <div class="d-flex align-center">
            <span>Signal Changepoints Map</span>
            <span class="map-instruction ml-2 text-medium-emphasis d-none d-md-inline">
              Click signals or segments to refine the table and chart.
            </span>
          </div>
          <v-spacer></v-spacer>
          <div v-if="selectionStore.hasMapSelections" class="d-flex align-center gap-2 flex-wrap">
            <v-chip size="small" color="info" variant="tonal" class="selection-chip">
              <span v-if="selectionStore.selectedSignals.size > 0">
                {{ selectionStore.selectedSignals.size }} signal(s)
              </span>
              <span v-if="selectionStore.selectedSignals.size > 0 && selectionStore.selectedXdSegments.size > 0">
                &bull;
              </span>
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
            data-type="changepoints"
            @selection-changed="onSelectionChanged"
          />
          <div
            v-else-if="!mapIsLoading"
            class="d-flex justify-center align-center loading-overlay"
          >
            <div class="text-h5 text-grey">No changepoints match the current filters</div>
          </div>
          <div v-if="mapIsLoading" class="d-flex justify-center align-center loading-overlay">
            <v-progress-circular indeterminate size="64"></v-progress-circular>
          </div>
        </v-card-text>
      </v-card>

      <v-card class="table-card">
        <v-card-title class="py-2 d-flex align-center flex-wrap">
          <div class="d-flex align-center">
            <v-icon left>mdi-table</v-icon>
            <span>Top Changepoints (limit 100)</span>
          </div>
          <v-spacer></v-spacer>
          <v-chip size="small" color="primary" variant="tonal">
            Sorted by: {{ activeSortLabel }}
          </v-chip>
        </v-card-title>
        <v-card-text>
          <VDataTableServer
            class="changepoints-table"
            :headers="tableHeaders"
            :items="tableRows"
            :items-length="tableTotal"
            :loading="tableIsLoading"
            :items-per-page="100"
            :sort-by="tableSortBy"
            :row-props="getRowProps"
            height="250"
            hide-default-footer
            @update:sort-by="onSortByChange"
            @click:row="onRowClick"
          >
            <template #item.timestamp="{ item }">
              {{ formatTimestamp(item.timestamp) }}
            </template>
            <template #item.pct_change="{ item }">
              {{ formatPercent(item.pct_change) }}
            </template>
            <template #item.avg_diff="{ item }">
              {{ formatSeconds(item.avg_diff) }}
            </template>
            <template #item.score="{ item }">
              {{ formatScore(item.score) }}
            </template>
            <template #item.road="{ item }">
              <div class="road-cell">
                <div class="font-weight-medium">{{ item.road_name }}</div>
                <div class="text-caption text-medium-emphasis">Bearing {{ item.bearing ?? '--' }}</div>
              </div>
            </template>
            <template #item.xd="{ item }">
              <code>{{ item.xd }}</code>
            </template>
            <template #no-data>
              <div class="d-flex justify-center py-6">
                <span class="text-medium-emphasis">No changepoints available. Adjust your filters.</span>
              </div>
            </template>
          </VDataTableServer>
        </v-card-text>
      </v-card>

      <v-card class="chart-card">
        <v-card-title class="py-2 d-flex align-center flex-wrap">
          <div class="d-flex align-center">
            <v-icon left>mdi-chart-line</v-icon>
            <span>Travel Time Before/After</span>
          </div>
          <v-spacer></v-spacer>
          <v-btn-toggle
            v-model="chartMode"
            mandatory
            density="compact"
            color="primary"
          >
            <v-btn value="date" size="small">
              By Date/Time
            </v-btn>
            <v-btn value="tod" size="small">
              By Time of Day
            </v-btn>
          </v-btn-toggle>
        </v-card-title>
        <v-card-text class="chart-container">
          <div v-if="!chartSelectionReady" class="d-flex justify-center align-center loading-overlay">
            <div class="text-medium-emphasis text-center px-6">
              Select a single changepoint row above to load the travel time comparison.
            </div>
          </div>
          <div v-else-if="chartIsLoading" class="d-flex justify-center align-center loading-overlay">
            <v-progress-circular indeterminate size="64"></v-progress-circular>
          </div>
          <div v-else-if="chartSeriesEmpty" class="d-flex justify-center align-center loading-overlay">
            <div class="text-medium-emphasis text-center px-6">
              No travel time samples were returned for the selected changepoint.
            </div>
          </div>
          <div v-else class="chart-shell">
            <ChangepointDetailChart
              :series="chartSeries"
              :is-time-of-day="chartMode === 'tod'"
              :title="chartTitle"
              :subtitle="chartSubtitle"
            />
          </div>
        </v-card-text>
      </v-card>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onActivated, onDeactivated, nextTick } from 'vue'
import SharedMap from '@/components/SharedMap.vue'
import ChangepointDetailChart from '@/components/ChangepointDetailChart.vue'
import { VDataTableServer } from 'vuetify/components'
import ApiService from '@/services/api'
import { useFiltersStore } from '@/stores/filters'
import { useSelectionStore } from '@/stores/selection'
import { useSignalDimensionsStore } from '@/stores/signalDimensions'
import { useXdDimensionsStore } from '@/stores/xdDimensions'
import { useThemeStore } from '@/stores/theme'
import { changepointColorScale } from '@/utils/colorScale'
import {
  normalizeChangepointDetailRow,
  buildChangepointDateSeries,
  buildChangepointTimeOfDaySeries
} from '@/utils/changepointSeries'

const filtersStore = useFiltersStore()
const selectionStore = useSelectionStore()
const signalDimensionsStore = useSignalDimensionsStore()
const xdDimensionsStore = useXdDimensionsStore()
const themeStore = useThemeStore()

const mapRef = ref(null)
const mapData = ref([])
const xdData = ref([])
const mapIsLoading = ref(true)
const shouldAutoZoomMap = ref(true)

const tableRows = ref([])
const tableTotal = ref(0)
const tableIsLoading = ref(true)
const tableSortBy = ref([{ key: 'pct_change', order: 'desc' }])

const selectedRow = ref(null)
const detailRows = ref([])
const chartMode = ref('date')
const chartIsLoading = ref(false)
const chartSeriesEmpty = ref(true)

const initialized = ref(false)
const lastSelectionState = ref(null)
let detailRequestId = 0

const legendBetterColor = computed(() => changepointColorScale(-5))
const legendNeutralColor = computed(() => changepointColorScale(0))
const legendWorseColor = computed(() => changepointColorScale(5))

const chartSelectionReady = computed(() => !!selectedRow.value)

const tableHeaders = [
  { title: 'Timestamp', value: 'timestamp', key: 'timestamp', sortable: true },
  { title: 'Pct Change', value: 'pct_change', key: 'pct_change', sortable: true },
  { title: 'Avg Diff (s)', value: 'avg_diff', key: 'avg_diff', sortable: true },
  { title: 'Score', value: 'score', key: 'score', sortable: true },
  { title: 'Road & Bearing', value: 'road', key: 'road', sortable: false },
  { title: 'XD', value: 'xd', key: 'xd', sortable: false }
]

const tableSortLabelMap = {
  timestamp: 'Timestamp',
  pct_change: 'Percent Change',
  avg_diff: 'Average Diff',
  score: 'Score'
}

const activeSortLabel = computed(() => {
  const current = tableSortBy.value[0]
  if (!current) return 'Timestamp (Newest)'
  const label = tableSortLabelMap[current.key] || 'Timestamp'
  const direction = current.order === 'asc' ? '(Low -> High)' : '(High -> Low)'
  return `${label} ${direction}`
})

const chartSeries = computed(() => {
  if (!detailRows.value.length) {
    return { before: [], after: [] }
  }
  return chartMode.value === 'tod'
    ? buildChangepointTimeOfDaySeries(detailRows.value)
    : buildChangepointDateSeries(detailRows.value)
})

const chartTitle = computed(() => {
  if (!selectedRow.value) {
    return 'Travel Time Before/After'
  }
  const row = selectedRow.value
  const xdLabel = row.xd ? `XD ${row.xd}` : 'Selected XD'
  const roadLabel = row.road_name || 'Changepoint Detail'
  return `${xdLabel} • ${roadLabel}`
})

const chartSubtitle = computed(() => {
  if (!selectedRow.value) {
    return 'Select a changepoint to compare travel times before and after the change.'
  }
  const row = selectedRow.value
  const timestampLabel = formatTimestamp(row.timestamp)
  const pctChange = row.pct_change !== undefined && row.pct_change !== null
    ? `${row.pct_change.toFixed(2)}%`
    : '--'
  return `Change Timestamp: ${timestampLabel} • Percent Change: ${pctChange}`
})

watch(
  () => buildFilterSignature(),
  async () => {
    if (!initialized.value) {
      return
    }
    resetDetailSelection()
    shouldAutoZoomMap.value = true
    await loadMapData({ autoZoom: true })
    await loadTableData()
  }
)

watch(
  () => buildSelectionSignature(),
  async (newVal, oldVal) => {
    if (!initialized.value) {
      return
    }
    if (newVal === oldVal) {
      return
    }
    resetDetailSelection()
    await loadTableData()
  }
)

watch(
  selectedRow,
  async (newRow) => {
    detailRequestId += 1
    const requestId = detailRequestId

    if (!newRow) {
      detailRows.value = []
      chartIsLoading.value = false
      chartSeriesEmpty.value = true
      return
    }

    chartIsLoading.value = true

    try {
      const params = {
        xd: newRow.xd,
        timestamp: newRow.timestamp
      }
      const arrowTable = await ApiService.getChangepointDetail(params)
      if (requestId !== detailRequestId) {
        return
      }

      const records = ApiService.arrowTableToObjects(arrowTable).map(normalizeChangepointDetailRow)
      detailRows.value = records
      chartSeriesEmpty.value = records.length === 0
    } catch (error) {
      if (requestId !== detailRequestId) {
        return
      }
      console.error('Failed to load changepoint detail data:', error)
      detailRows.value = []
      chartSeriesEmpty.value = true
    } finally {
      if (requestId === detailRequestId) {
        chartIsLoading.value = false
      }
    }
  }
)

// Auto-select first row when table loads or changes
watch(
  tableRows,
  (newRows) => {
    // Always select first row if no selection or if current selection is not in the new rows
    if (newRows.length > 0) {
      if (!selectedRow.value) {
        // No selection, select first row
        selectedRow.value = { ...newRows[0] }
      } else {
        // Check if current selection still exists in new rows
        const currentKey = selectedRow.value.rowKey
        const stillExists = newRows.find(row => getRowKey(row) === currentKey)
        if (!stillExists) {
          // Current selection is gone, select first row
          selectedRow.value = { ...newRows[0] }
        }
      }
    }
  }
)

onMounted(async () => {
  try {
    await ensureDimensions()
  } catch (error) {
    console.error('Failed to load dimension data for changepoints:', error)
  }

  await loadAllData({ autoZoom: true })
  initialized.value = true
  lastSelectionState.value = captureSelectionState()
})

onActivated(async () => {
  if (!initialized.value) {
    return
  }
  const currentState = captureSelectionState()
  if (
    !lastSelectionState.value ||
    currentState.signals !== lastSelectionState.value.signals ||
    currentState.xdSegments !== lastSelectionState.value.xdSegments
  ) {
    resetDetailSelection()
    await loadTableData()
  }
  lastSelectionState.value = currentState
})

onDeactivated(() => {
  lastSelectionState.value = captureSelectionState()
})

function captureSelectionState() {
  return {
    signalsSize: selectionStore.selectedSignals.size,
    xdSegmentsSize: selectionStore.selectedXdSegments.size,
    signals: Array.from(selectionStore.selectedSignals).sort().join(','),
    xdSegments: Array.from(selectionStore.selectedXdSegments).sort().join(',')
  }
}

async function ensureDimensions() {
  await Promise.all([
    signalDimensionsStore.loadDimensions(),
    xdDimensionsStore.loadDimensions()
  ])
}

function buildFilterSignature() {
  const params = filtersStore.changepointFilterParams
  return JSON.stringify({
    start_date: params.start_date,
    end_date: params.end_date,
    maintained_by: params.maintained_by,
    approach: params.approach,
    valid_geometry: params.valid_geometry,
    pct_change_improvement: params.pct_change_improvement,
    pct_change_degradation: params.pct_change_degradation,
    signal_ids: (params.signal_ids || []).slice().sort()
  })
}

function buildSelectionSignature() {
  return JSON.stringify({
    signals: Array.from(selectionStore.selectedSignals).sort(),
    xds: Array.from(selectionStore.selectedXdSegments).sort()
  })
}

function buildBaseFilterParams() {
  const params = { ...filtersStore.changepointFilterParams }

  if (params.signal_ids && params.signal_ids.length > 0) {
    params.signal_ids = params.signal_ids.slice()
  } else {
    delete params.signal_ids
  }

  if (params.approach === null || params.approach === undefined) {
    delete params.approach
  }
  if (params.valid_geometry === undefined) {
    delete params.valid_geometry
  }
  if (params.maintained_by === undefined) {
    delete params.maintained_by
  }

  return params
}

function buildMapParams() {
  return buildBaseFilterParams()
}

function buildTableParams() {
  const params = buildBaseFilterParams()
  const sort = tableSortBy.value[0] || { key: 'pct_change', order: 'desc' }
  params.sort_by = sort.key
  params.sort_dir = sort.order === 'asc' ? 'asc' : 'desc'

  if (selectionStore.selectedSignals.size > 0) {
    params.selected_signals = Array.from(selectionStore.selectedSignals)
  }
  if (selectionStore.selectedXdSegments.size > 0) {
    params.selected_xds = Array.from(selectionStore.selectedXdSegments)
  }

  return params
}

async function loadAllData({ autoZoom = false } = {}) {
  await loadMapData({ autoZoom })
  await loadTableData()
}

async function loadMapData({ autoZoom = false } = {}) {
  mapIsLoading.value = true
  shouldAutoZoomMap.value = autoZoom

  try {
    const params = buildMapParams()
    const [signalsTable, xdTable] = await Promise.all([
      ApiService.getChangepointMapSignals(params),
      ApiService.getChangepointMapXd(params)
    ])

    const signalRows = ApiService.arrowTableToObjects(signalsTable)
    const xdRows = ApiService.arrowTableToObjects(xdTable)

    const enrichedSignals = signalRows
      .map(row => {
        const dimensions = signalDimensionsStore.getSignalDimensions(row.ID)
        if (!dimensions || dimensions.LATITUDE == null || dimensions.LONGITUDE == null) {
          return null
        }
        return {
          ID: row.ID,
          ABS_PCT_SUM: Number(row.ABS_PCT_SUM ?? 0),
          AVG_PCT_CHANGE: Number(row.AVG_PCT_CHANGE ?? 0),
          CHANGEPOINT_COUNT: Number(row.CHANGEPOINT_COUNT ?? 0),
          TOP_XD: row.TOP_XD,
          TOP_TIMESTAMP: row.TOP_TIMESTAMP,
          TOP_PCT_CHANGE: Number(row.TOP_PCT_CHANGE ?? 0),
          TOP_AVG_DIFF: Number(row.TOP_AVG_DIFF ?? 0),
          TOP_ROADNAME: row.TOP_ROADNAME,
          TOP_BEARING: row.TOP_BEARING,
          LATITUDE: dimensions.LATITUDE,
          LONGITUDE: dimensions.LONGITUDE,
          NAME: dimensions.NAME
        }
      })
      .filter(Boolean)

    const enrichedXd = xdRows.map(row => {
      const dimensions = xdDimensionsStore.getXdDimensions(row.XD) || {}
      return {
        XD: row.XD,
        SIGNAL_ID: row.SIGNAL_ID ?? dimensions.ID,
        ABS_PCT_SUM: Number(row.ABS_PCT_SUM ?? 0),
        AVG_PCT_CHANGE: Number(row.AVG_PCT_CHANGE ?? 0),
        CHANGEPOINT_COUNT: Number(row.CHANGEPOINT_COUNT ?? 0),
        TOP_TIMESTAMP: row.TOP_TIMESTAMP,
        TOP_PCT_CHANGE: Number(row.TOP_PCT_CHANGE ?? 0),
        TOP_AVG_DIFF: Number(row.TOP_AVG_DIFF ?? 0),
        TOP_ROADNAME: row.TOP_ROADNAME ?? dimensions.ROADNAME,
        TOP_BEARING: row.TOP_BEARING ?? dimensions.BEARING
      }
    })

    mapData.value = enrichedSignals
    xdData.value = enrichedXd
    selectionStore.updateMappings(enrichedSignals, enrichedXd)

    if (autoZoom) {
      await nextTick()
      const mapInstance = mapRef.value
      if (mapInstance && typeof mapInstance.rezoomToSignals === 'function') {
        mapInstance.rezoomToSignals()
      }
    }
  } catch (error) {
    console.error('Failed to load changepoint map data:', error)
    mapData.value = []
    xdData.value = []
    selectionStore.updateMappings([], [])
  } finally {
    mapIsLoading.value = false
  }
}

async function loadTableData() {
  tableIsLoading.value = true
  try {
    const params = buildTableParams()
    const table = await ApiService.getChangepointTable(params)
    const rows = ApiService.arrowTableToObjects(table)

    const processed = rows.map(row => ({
      rowKey: `${row.XD}-${row.TIMESTAMP}`,
      timestamp: row.TIMESTAMP,
      pct_change: Number(row.PCT_CHANGE ?? 0),
      avg_diff: Number(row.AVG_DIFF ?? 0),
      score: Number(row.SCORE ?? 0),
      road_name: row.ROADNAME,
      bearing: row.BEARING,
      xd: row.XD,
      id: row.ID,
      avg_before: Number(row.AVG_BEFORE ?? 0),
      avg_after: Number(row.AVG_AFTER ?? 0)
    }))

    tableRows.value = processed
    tableTotal.value = processed.length

    if (selectedRow.value) {
      const stillExists = processed.find(row => row.rowKey === selectedRow.value.rowKey)
      if (!stillExists) {
        selectedRow.value = null
      }
    }
  } catch (error) {
    console.error('Failed to load changepoint table data:', error)
    tableRows.value = []
    tableTotal.value = 0
    selectedRow.value = null
  } finally {
    tableIsLoading.value = false
  }
}

function resetDetailSelection() {
  if (selectedRow.value) {
    selectedRow.value = null
    return
  }
  detailRows.value = []
  chartIsLoading.value = false
  chartSeriesEmpty.value = true
}

function clearMapSelections() {
  selectionStore.clearAllSelections()
}

function onSelectionChanged(payload) {
  console.debug('Changepoints map selection changed', payload)
}

function onSortByChange(sortBy) {
    tableSortBy.value = sortBy.length > 0 ? sortBy : [{ key: 'pct_change', order: 'desc' }]
    loadTableData()
}

function onRowClick(event, row) {
  const clicked = row.item
  if (!clicked) {
    return
  }

  const clickedKey = getRowKey(clicked)

  // Don't deselect if clicking on already-selected row
  if (selectedRow.value && selectedRow.value.rowKey === clickedKey) {
    return
  }

  selectedRow.value = { ...clicked, rowKey: clickedKey }
}

function getRowKey(item) {
  if (!item) return ''
  if (item.rowKey) return item.rowKey
  const timestampPart = item.timestamp || item.TIMESTAMP || 'unknown'
  const xdPart = item.xd || item.XD || 'unknown'
  return `${xdPart}-${timestampPart}`
}

function getRowProps({ item }) {
  if (!item) {
    return {}
  }
  const key = getRowKey(item)
  if (!key) {
    return {}
  }
  const isSelected = selectedRow.value && selectedRow.value.rowKey === key

  if (isSelected) {
    // Use inline styles following Vuetify theme colors
    const primaryColor = themeStore.isDark ? 'rgba(144, 202, 249, 0.16)' : 'rgba(25, 118, 210, 0.12)'
    const borderColor = themeStore.isDark ? '#90caf9' : '#1976d2'

    return {
      style: {
        backgroundColor: primaryColor,
        borderLeft: `4px solid ${borderColor}`,
        fontWeight: '500',
        cursor: 'pointer'
      }
    }
  }

  return {
    style: { cursor: 'pointer' }
  }
}

function formatTimestamp(value) {
  if (!value) return '--'
  return new Date(value).toLocaleString()
}

function formatPercent(value) {
  if (value === null || value === undefined) return '--'
  return `${(value * 100).toFixed(1)}%`
}

function formatSeconds(value) {
  if (value === null || value === undefined) return '--'
  return `${value.toFixed(1)} s`
}

function formatScore(value) {
  if (value === null || value === undefined) return '--'
  return value.toFixed(1)
}
</script>

<style scoped>
.changepoints-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.content-grid {
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: 1fr auto 1fr;
  gap: 12px;
  flex: 1;
  min-height: 0;
}

.map-card,
.table-card,
.chart-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  position: relative;
}

.map-container {
  flex: 1;
  position: relative;
  min-height: 0;
  padding: 0;
}

.loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.selection-chip {
  font-size: 0.85rem;
}

.legend-container {
  gap: 8px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-circle {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(var(--v-theme-on-surface), 0.4);
}

.legend-text {
  font-size: 0.85rem;
}

.map-instruction {
  font-size: 0.9rem;
}

.table-card .v-card-text {
  padding: 12px !important;
}

.changepoints-table {
  --v-data-table-header-height: 44px;
}

.road-cell {
  display: flex;
  flex-direction: column;
}


.chart-container {
  flex: 1;
  position: relative;
  min-height: 0;
  padding: 12px !important;
}

.chart-shell {
  height: 100%;
}

@media (max-width: 960px) {
  .content-grid {
    grid-template-rows: auto auto auto;
  }

  .map-container,
  .chart-container {
    min-height: 250px;
  }
}
</style>
