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
          <v-checkbox
            v-model="filtersStore.timeFilterEnabled"
            label="Filter by Time of Day"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>

      <v-row v-if="filtersStore.timeFilterEnabled">
        <v-col cols="12">
          <div class="text-caption mb-2">
            {{ formatTime(filtersStore.startHour) }} - {{ formatTime(filtersStore.endHour) }}
          </div>
          <v-range-slider
            :model-value="timeRange"
            @end="updateTimeRange"
            :min="0"
            :max="23"
            :step="1"
            thumb-label="always"
            density="compact"
            color="primary"
          >
            <template v-slot:thumb-label="{ modelValue }">
              {{ formatTime(modelValue) }}
            </template>
          </v-range-slider>
        </v-col>
      </v-row>

      <!-- Filter Summary -->
      <v-divider class="my-4"></v-divider>
      <v-card variant="tonal" class="mb-2">
        <v-card-text>
          <div class="text-caption">
            <div><strong>Date Range:</strong> {{ filtersStore.startDate }} to {{ filtersStore.endDate }}</div>
            <div><strong>Aggregation:</strong> {{ filtersStore.aggregationLevel }}</div>
            <div><strong>Signals:</strong> {{ filtersStore.selectedSignalIds.length || 'All' }}</div>
            <div v-if="filtersStore.approach !== null"><strong>Approach:</strong> {{ filtersStore.approach ? 'True' : 'False' }}</div>
            <div v-if="filtersStore.validGeometry !== null"><strong>Valid Geometry:</strong> {{ validGeometryDisplayText }}</div>
            <div v-if="$route.name === 'Anomalies'"><strong>Anomaly Type:</strong> {{ filtersStore.anomalyType }}</div>
            <div v-if="filtersStore.timeFilterEnabled"><strong>Time of Day:</strong> {{ formatTime(filtersStore.startHour) }} - {{ formatTime(filtersStore.endHour) }}</div>
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

// Display value for range slider
const timeRange = computed(() => [filtersStore.startHour, filtersStore.endHour])

// Update time range only when slider is released
function updateTimeRange(value) {
  filtersStore.setTimeOfDayRange(value[0], value[1])
}

// Format hour to HH:00 time string
function formatTime(hour) {
  return `${String(hour).padStart(2, '0')}:00`
}

const signalOptions = computed(() => {
  // Deduplicate signal IDs - DIM_SIGNALS_XD has multiple rows per signal
  const uniqueSignalIds = [...new Set(signals.value.map(signal => signal.ID))]
  return uniqueSignalIds.map(id => ({
    text: `Signal ${id}`,
    value: id
  }))
})

const validGeometryDisplayText = computed(() => {
  if (filtersStore.validGeometry === 'valid') return 'Valid Only'
  if (filtersStore.validGeometry === 'invalid') return 'Invalid Only'
  if (filtersStore.validGeometry === 'all') return 'All'
  return 'All'
})

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

onMounted(async () => {
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