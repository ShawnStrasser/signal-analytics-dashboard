<template>
  <v-card class="ma-2" elevation="0">
    <v-card-title>
      <v-icon left>mdi-filter</v-icon>
      Filters
    </v-card-title>
    
    <v-card-text>
      <!-- Date Range (conditionally show Before/After selector or standard date range) -->
      <BeforeAfterDateSelector v-if="$route.name === 'BeforeAfter'" />
      <v-row v-else>
        <v-col cols="12">
          <v-text-field
            v-model="localStartDate"
            label="Start Date"
            type="date"
            density="compact"
            variant="outlined"
          />
        </v-col>
        <v-col cols="12">
          <v-text-field
            v-model="localEndDate"
            label="End Date"
            type="date"
            density="compact"
            variant="outlined"
          />
        </v-col>
      </v-row>

      <!-- Maintained By Filter -->
      <v-row>
        <v-col cols="12">
          <v-select
            v-model="filtersStore.maintainedBy"
            :items="maintainedByOptions"
            label="Maintained By"
            density="compact"
            variant="outlined"
          />
        </v-col>
      </v-row>

      <!-- Hierarchical District & Signal Selection -->
      <v-row>
        <v-col cols="12">
          <v-card variant="outlined">
            <!-- Collapsible header -->
            <v-card-subtitle
              class="py-2 d-flex align-center justify-space-between signal-selector-header"
              @click="signalSelectorExpanded = !signalSelectorExpanded"
              style="cursor: pointer;"
            >
              <span>Select Signals</span>
              <v-icon>{{ signalSelectorExpanded ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
            </v-card-subtitle>

            <v-expand-transition>
              <v-card-text v-show="signalSelectorExpanded" class="py-2">
                <!-- Search bar -->
                <v-text-field
                  v-model="searchQuery"
                  prepend-inner-icon="mdi-magnify"
                  label="Search signals..."
                  density="compact"
                  variant="outlined"
                  clearable
                  hide-details
                  class="mb-2"
                />

                <!-- District groups -->
                <div v-if="signalsStore.loading" class="text-center py-4">
                  <v-progress-circular indeterminate size="32"></v-progress-circular>
                </div>
                <div v-else-if="Object.keys(filteredDistrictGroups).length === 0" class="text-caption text-grey py-2">
                  No signals found
                </div>
                <v-expansion-panels v-else multiple variant="accordion" class="district-panels">
                  <v-expansion-panel
                    v-for="(districtSignals, district) in filteredDistrictGroups"
                    :key="district"
                    :title="`${district} (${districtSignals.length} signals)`"
                    class="district-panel-item"
                  >
                    <template v-slot:title>
                      <div class="d-flex align-center" style="width: 100%;">
                        <v-checkbox
                          :model-value="isDistrictSelected(district)"
                          :indeterminate="isDistrictIndeterminate(district)"
                          @click.stop="toggleDistrict(district)"
                          hide-details
                          density="compact"
                          class="flex-shrink-0 mr-2"
                        />
                        <span class="district-name">{{ district }}</span>
                      </div>
                    </template>
                    <v-expansion-panel-text>
                      <div
                        v-for="(signal, index) in districtSignals"
                        :key="signal.ID"
                        class="signal-item"
                        :class="{ 'with-divider': index < districtSignals.length - 1 }"
                      >
                        <v-checkbox
                          :model-value="filtersStore.selectedSignalIds.includes(signal.ID)"
                          @update:model-value="toggleSignal(signal.ID)"
                          :label="`${signal.ID} - ${signal.NAME || 'Unknown'}`"
                          hide-details
                          density="compact"
                        />
                      </div>
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>

                <!-- Clear all button -->
                <v-btn
                  v-if="filtersStore.selectedSignalIds.length > 0"
                  block
                  size="small"
                  variant="outlined"
                  color="error"
                  class="mt-2"
                  @click="clearAllSignals"
                >
                  Clear All ({{ filtersStore.selectedSignalIds.length }} selected)
                </v-btn>
              </v-card-text>
            </v-expand-transition>
          </v-card>
        </v-col>
      </v-row>

      <!-- Approach Filter -->
      <v-row>
        <v-col cols="12">
          <v-select
            v-model="filtersStore.approach"
            :items="approachOptions"
            label="Approach"
            density="compact"
            variant="outlined"
            clearable
          />
        </v-col>
      </v-row>

      <!-- Valid Geometry Filter -->
      <v-row>
        <v-col cols="12">
          <v-select
            v-model="filtersStore.validGeometry"
            :items="validGeometryOptions"
            label="Valid Geometry"
            density="compact"
            variant="outlined"
            clearable
          />
        </v-col>
      </v-row>

      <!-- Anomaly Type Filter (only shown on anomalies page) -->
      <v-row v-if="$route.name === 'Anomalies'">
        <v-col cols="12">
          <v-select
            v-model="filtersStore.anomalyType"
            :items="anomalyTypeOptions"
            label="Anomaly Type"
            density="compact"
            variant="outlined"
          />
        </v-col>
      </v-row>

      <!-- Time of Day Filter -->
      <v-row>
        <v-col cols="12">
          <fieldset style="border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 4px; padding: 32px 12px 12px 12px;">
            <legend style="padding: 0 4px; margin-left: 8px; font-size: 0.75rem; color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));">Time of Day</legend>
            <v-range-slider
              :model-value="timeRangeQuarters"
              @end="updateTimeRangeQuarters"
              :min="sliderMin"
              :max="sliderMax"
              :step="1"
              thumb-label="always"
              density="compact"
              color="primary"
              hide-details
            >
              <template v-slot:thumb-label="{ modelValue }">
                {{ formatQuarterHour(modelValue) }}
              </template>
            </v-range-slider>
          </fieldset>
        </v-col>
      </v-row>

      <!-- Day of Week Filter -->
      <v-row>
        <v-col cols="12">
          <v-select
            v-model="filtersStore.dayOfWeek"
            :items="dayOfWeekOptions"
            label="Day of Week"
            multiple
            chips
            density="compact"
            variant="outlined"
            clearable
          />
        </v-col>
      </v-row>

      <!-- Remove Anomalies Filter (only shown on Travel Time and Before/After pages) -->
      <v-row v-if="$route.name === 'TravelTime' || $route.name === 'BeforeAfter'">
        <v-col cols="12">
          <v-checkbox
            v-model="filtersStore.removeAnomalies"
            label="Remove Anomalies"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>

      <!-- Filter Summary -->
      <v-divider class="my-4"></v-divider>
      <v-card variant="tonal" class="mb-2">
        <v-card-text>
          <div class="text-caption">
            <div v-if="$route.name === 'BeforeAfter'">
              <div><strong>Before:</strong> {{ beforeAfterFiltersStore.beforeStartDate }} to {{ beforeAfterFiltersStore.beforeEndDate }}</div>
              <div><strong>After:</strong> {{ beforeAfterFiltersStore.afterStartDate }} to {{ beforeAfterFiltersStore.afterEndDate }}</div>
            </div>
            <div v-else>
              <div><strong>Date Range:</strong> {{ filtersStore.startDate }} to {{ filtersStore.endDate }}</div>
              <div><strong>Aggregation:</strong> {{ filtersStore.aggregationLevel }}</div>
            </div>
            <div v-if="filtersStore.maintainedBy !== 'all'"><strong>Maintained By:</strong> {{ maintainedByDisplayText }}</div>
            <div><strong>Signals:</strong> {{ filtersStore.selectedSignalIds.length || 'All' }}</div>
            <div v-if="filtersStore.approach !== null"><strong>Approach:</strong> {{ filtersStore.approach ? 'True' : 'False' }}</div>
            <div v-if="filtersStore.validGeometry !== null"><strong>Valid Geometry:</strong> {{ validGeometryDisplayText }}</div>
            <div v-if="$route.name === 'Anomalies'"><strong>Anomaly Type:</strong> {{ filtersStore.anomalyType }}</div>
            <div><strong>Time of Day:</strong> {{ formatTimeDetailed(filtersStore.startHour, filtersStore.startMinute) }} - {{ formatTimeDetailed(filtersStore.endHour, filtersStore.endMinute) }}</div>
            <div v-if="filtersStore.dayOfWeek.length > 0"><strong>Days:</strong> {{ dayOfWeekDisplayText }}</div>
            <div v-if="($route.name === 'TravelTime' || $route.name === 'BeforeAfter') && filtersStore.removeAnomalies"><strong>Remove Anomalies:</strong> Yes</div>
          </div>
        </v-card-text>
      </v-card>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useFiltersStore } from '@/stores/filters'
import { useSignalsStore } from '@/stores/signals'
import { useBeforeAfterFiltersStore } from '@/stores/beforeAfterFilters'
import ApiService from '@/services/api'
import BeforeAfterDateSelector from './BeforeAfterDateSelector.vue'

const filtersStore = useFiltersStore()
const signalsStore = useSignalsStore()
const beforeAfterFiltersStore = useBeforeAfterFiltersStore()
const loadingSignals = ref(false)
const signals = ref([]) // Keep for backward compat with old DIM_SIGNALS_XD endpoint
const searchQuery = ref('')
const signalSelectorExpanded = ref(true) // Start expanded by default

// Local date state with debouncing
const localStartDate = ref(filtersStore.startDate)
const localEndDate = ref(filtersStore.endDate)
let dateDebounceTimer = null

// Watch for external changes to store (e.g., programmatic updates)
watch(() => filtersStore.startDate, (newVal) => {
  if (newVal !== localStartDate.value) {
    localStartDate.value = newVal
  }
})

watch(() => filtersStore.endDate, (newVal) => {
  if (newVal !== localEndDate.value) {
    localEndDate.value = newVal
  }
})

// Debounced update of store when local values change
watch([localStartDate, localEndDate], ([newStart, newEnd]) => {
  clearTimeout(dateDebounceTimer)
  dateDebounceTimer = setTimeout(() => {
    if (newStart !== filtersStore.startDate || newEnd !== filtersStore.endDate) {
      filtersStore.setDateRange(newStart, newEnd)
    }
  }, 500) // 500ms debounce delay
})

// Slider min/max in quarter-hour units (computed from config)
const sliderMin = computed(() => timeToQuarters(filtersStore.defaultStartHour, 0))
const sliderMax = computed(() => timeToQuarters(filtersStore.defaultEndHour, 0))

// Convert hour/minute to quarter-hour index (0-95)
function timeToQuarters(hour, minute) {
  return hour * 4 + Math.floor(minute / 15)
}

// Convert quarter-hour index to hour and minute
function quartersToTime(quarters) {
  const hour = Math.floor(quarters / 4)
  const minute = (quarters % 4) * 15
  return { hour, minute }
}

// Display value for range slider (in quarter-hour units)
const timeRangeQuarters = computed(() => [
  timeToQuarters(filtersStore.startHour, filtersStore.startMinute),
  timeToQuarters(filtersStore.endHour, filtersStore.endMinute)
])

// Update time range when slider is released
function updateTimeRangeQuarters(value) {
  const start = quartersToTime(value[0])
  const end = quartersToTime(value[1])
  filtersStore.setTimeOfDayRange(start.hour, start.minute, end.hour, end.minute)
}

// Format quarter-hour index to HH:MM time string
function formatQuarterHour(quarters) {
  const { hour, minute } = quartersToTime(quarters)
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

// Format hour and minute to HH:MM time string
function formatTimeDetailed(hour, minute) {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

// Format hour to HH:00 time string (kept for filter summary)
function formatTime(hour) {
  return `${String(hour).padStart(2, '0')}:00`
}

// Filter district groups by search query
const filteredDistrictGroups = computed(() => {
  const groups = signalsStore.signalsByDistrict

  if (!searchQuery.value) {
    return groups
  }

  const query = searchQuery.value.toLowerCase()
  const filtered = {}

  Object.entries(groups).forEach(([district, signalList]) => {
    const matchingSignals = signalList.filter(signal => {
      const idMatch = signal.ID.toLowerCase().includes(query)
      const nameMatch = signal.NAME?.toLowerCase().includes(query)
      const districtMatch = district.toLowerCase().includes(query)
      return idMatch || nameMatch || districtMatch
    })

    if (matchingSignals.length > 0) {
      filtered[district] = matchingSignals
    }
  })

  return filtered
})

// Check if all signals in a district are selected
function isDistrictSelected(district) {
  const districtSignals = signalsStore.signalsByDistrict[district]
  if (!districtSignals || districtSignals.length === 0) return false

  return districtSignals.every(signal =>
    filtersStore.selectedSignalIds.includes(signal.ID)
  )
}

// Check if some (but not all) signals in a district are selected
function isDistrictIndeterminate(district) {
  const districtSignals = signalsStore.signalsByDistrict[district]
  if (!districtSignals || districtSignals.length === 0) return false

  const selectedCount = districtSignals.filter(signal =>
    filtersStore.selectedSignalIds.includes(signal.ID)
  ).length

  return selectedCount > 0 && selectedCount < districtSignals.length
}

// Toggle all signals in a district
function toggleDistrict(district) {
  const districtSignals = signalsStore.signalsByDistrict[district]
  if (!districtSignals) return

  const allSelected = isDistrictSelected(district)

  if (allSelected) {
    // Deselect all signals in this district
    const districtSignalIds = districtSignals.map(s => s.ID)
    filtersStore.selectedSignalIds = filtersStore.selectedSignalIds.filter(
      id => !districtSignalIds.includes(id)
    )
  } else {
    // Select all signals in this district
    const districtSignalIds = districtSignals.map(s => s.ID)
    const newIds = [...new Set([...filtersStore.selectedSignalIds, ...districtSignalIds])]
    filtersStore.selectedSignalIds = newIds
  }
}

// Toggle individual signal selection
function toggleSignal(signalId) {
  const index = filtersStore.selectedSignalIds.indexOf(signalId)

  if (index > -1) {
    // Deselect
    filtersStore.selectedSignalIds = filtersStore.selectedSignalIds.filter(id => id !== signalId)
  } else {
    // Select
    filtersStore.selectedSignalIds = [...filtersStore.selectedSignalIds, signalId]
  }
}

// Clear all signal selections
function clearAllSignals() {
  filtersStore.selectedSignalIds = []
}

const validGeometryDisplayText = computed(() => {
  if (filtersStore.validGeometry === 'valid') return 'Valid Only'
  if (filtersStore.validGeometry === 'invalid') return 'Invalid Only'
  if (filtersStore.validGeometry === 'all') return 'All'
  return 'All'
})

const maintainedByDisplayText = computed(() => {
  if (filtersStore.maintainedBy === 'odot') return 'ODOT'
  if (filtersStore.maintainedBy === 'others') return 'Others'
  return 'All'
})

const maintainedByOptions = [
  { title: 'All', value: 'all' },
  { title: 'ODOT', value: 'odot' },
  { title: 'Others', value: 'others' }
]

const approachOptions = [
  { title: 'True', value: true },
  { title: 'False', value: false }
]

const validGeometryOptions = [
  { title: 'All', value: 'all' },
  { title: 'Valid Only', value: 'valid' },
  { title: 'Invalid Only', value: 'invalid' }
]

const anomalyTypeOptions = [
  { title: 'All Anomalies', value: 'All' },
  { title: 'Point Source', value: 'Point Source' }
]

const dayOfWeekOptions = [
  { title: 'Mon', value: 1 },
  { title: 'Tue', value: 2 },
  { title: 'Wed', value: 3 },
  { title: 'Thu', value: 4 },
  { title: 'Fri', value: 5 },
  { title: 'Sat', value: 6 },
  { title: 'Sun', value: 7 }
]

const dayOfWeekDisplayText = computed(() => {
  if (filtersStore.dayOfWeek.length === 0) return ''
  const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  return filtersStore.dayOfWeek
    .map(d => dayNames[d - 1])
    .join(', ')
})

onMounted(async () => {
  await filtersStore.initializeConfig()

  // Load DIM_SIGNALS data for hierarchical UI
  try {
    await signalsStore.loadDimSignals()
  } catch (error) {
    console.error('Failed to load DIM_SIGNALS data:', error)
  }

  // Keep loading old endpoint for backward compat (if needed elsewhere)
  await loadSignals()
})

async function loadSignals() {
  try {
    loadingSignals.value = true
    const arrowTable = await ApiService.getSignals()
    signals.value = ApiService.arrowTableToObjects(arrowTable)
  } catch (error) {
    console.error('Failed to load signals:', error)
  } finally {
    loadingSignals.value = false
  }
}
</script>

<style scoped>
/* Collapsible signal selector header */
.signal-selector-header {
  user-select: none;
  transition: background-color 0.2s;
  font-size: 0.95rem !important;
}

.signal-selector-header:hover {
  background-color: rgba(var(--v-theme-on-surface), 0.04);
}

/* Taller district panels with scrolling */
.district-panels {
  max-height: 600px;
  overflow-y: auto;
}

/* Reduce spacing between district panels */
.district-panels :deep(.v-expansion-panel) {
  margin-bottom: 2px !important;
}

.district-panels :deep(.v-expansion-panel:not(:first-child)::after) {
  border-top: none;
}

.district-panels :deep(.v-expansion-panel-title) {
  min-height: 40px !important;
  padding: 8px 12px !important;
}

/* Make district name text stand out more */
.district-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  font-size: 0.9rem;
}

/* Signal item styling with separators */
.signal-item {
  padding: 4px 0;
}

.signal-item.with-divider {
  border-bottom: 1px solid rgba(var(--v-border-color), 0.12);
  margin-bottom: 4px;
  padding-bottom: 8px;
}
</style>