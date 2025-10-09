<template>
  <v-card class="ma-2" elevation="0">
    <v-card-title>
      <v-icon left>mdi-filter</v-icon>
      Filters
    </v-card-title>
    
    <v-card-text>
      <!-- Date Range -->
      <v-row>
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

      <!-- Signal Selection -->
      <v-row>
        <v-col cols="12">
          <v-autocomplete
            v-model="filtersStore.selectedSignalIds"
            :items="signalOptions"
            item-title="text"
            item-value="value"
            label="Select Signals"
            multiple
            chips
            density="compact"
            variant="outlined"
            :loading="loadingSignals"
            clearable
          />
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

      <!-- Filter Summary -->
      <v-divider class="my-4"></v-divider>
      <v-card variant="tonal" class="mb-2">
        <v-card-text>
          <div class="text-caption">
            <div><strong>Date Range:</strong> {{ filtersStore.startDate }} to {{ filtersStore.endDate }}</div>
            <div><strong>Aggregation:</strong> {{ filtersStore.aggregationLevel }}</div>
            <div v-if="filtersStore.maintainedBy !== 'all'"><strong>Maintained By:</strong> {{ maintainedByDisplayText }}</div>
            <div><strong>Signals:</strong> {{ filtersStore.selectedSignalIds.length || 'All' }}</div>
            <div v-if="filtersStore.approach !== null"><strong>Approach:</strong> {{ filtersStore.approach ? 'True' : 'False' }}</div>
            <div v-if="filtersStore.validGeometry !== null"><strong>Valid Geometry:</strong> {{ validGeometryDisplayText }}</div>
            <div v-if="$route.name === 'Anomalies'"><strong>Anomaly Type:</strong> {{ filtersStore.anomalyType }}</div>
            <div><strong>Time of Day:</strong> {{ formatTimeDetailed(filtersStore.startHour, filtersStore.startMinute) }} - {{ formatTimeDetailed(filtersStore.endHour, filtersStore.endMinute) }}</div>
            <div v-if="filtersStore.dayOfWeek.length > 0"><strong>Days:</strong> {{ dayOfWeekDisplayText }}</div>
          </div>
        </v-card-text>
      </v-card>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useFiltersStore } from '@/stores/filters'
import ApiService from '@/services/api'

const filtersStore = useFiltersStore()
const loadingSignals = ref(false)
const signals = ref([])

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

// Group signals by district (when district data becomes available)
const signalsByDistrict = computed(() => {
  // Filter signals by maintainedBy if not 'all'
  let filteredSignals = signals.value

  // Note: When backend is updated to use DIM_SIGNALS with ODOT_MAINTAINED column,
  // uncomment this filtering logic:
  // if (filtersStore.maintainedBy === 'odot') {
  //   filteredSignals = filteredSignals.filter(s => s.ODOT_MAINTAINED === true)
  // } else if (filtersStore.maintainedBy === 'others') {
  //   filteredSignals = filteredSignals.filter(s => s.ODOT_MAINTAINED === false)
  // }

  // Deduplicate signal IDs - DIM_SIGNALS_XD has multiple rows per signal
  const uniqueSignalIds = [...new Set(filteredSignals.map(signal => signal.ID))]

  // Group by district when DISTRICT column is available
  // For now, return a flat structure until backend provides district data
  const grouped = {}
  uniqueSignalIds.forEach(id => {
    const district = 'Unknown' // Replace with s.DISTRICT when available
    if (!grouped[district]) {
      grouped[district] = []
    }
    grouped[district].push(id)
  })

  return grouped
})

const signalOptions = computed(() => {
  // Flat list for autocomplete - will be enhanced for hierarchical selection later
  const allDistricts = signalsByDistrict.value
  const flatList = []

  Object.entries(allDistricts).forEach(([district, signalIds]) => {
    signalIds.forEach(id => {
      flatList.push({
        text: `Signal ${id}`,
        value: id
      })
    })
  })

  return flatList
})

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