import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useFiltersStore = defineStore('filters', () => {
  // Config values from backend (will be populated on init)
  const defaultStartHour = ref(6)   // Default from config.py
  const defaultEndHour = ref(19)    // Default from config.py

  // State
  const startDate = ref(new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]) // 2 days ago
  const endDate = ref(new Date().toISOString().split('T')[0]) // Today
  const selectedSignalIds = ref([])
  const approach = ref(null)
  const validGeometry = ref('all') // 'all', 'valid', or 'invalid'
  const anomalyType = ref('All')
  const startHour = ref(6)   // Will be set from config
  const startMinute = ref(0)
  const endHour = ref(19)    // Will be set from config
  const endMinute = ref(0)
  const timeFilterEnabled = ref(true)  // Time-of-day filter always enabled
  const dayOfWeek = ref([])  // Selected days of week (1=Mon, 2=Tue, ..., 7=Sun)

  // Computed
  const hasSignalFilters = computed(() => selectedSignalIds.value.length > 0)

  // Check if time range is at default (full data range)
  const isDefaultTimeRange = computed(() =>
    startHour.value === defaultStartHour.value && startMinute.value === 0 &&
    endHour.value === defaultEndHour.value && endMinute.value === 0
  )

  const aggregationLevel = computed(() => {
    try {
      const start = new Date(startDate.value)
      const end = new Date(endDate.value)
      const days = Math.ceil((end - start) / (1000 * 60 * 60 * 24))

      if (days < 4) return '15min'
      if (days <= 7) return 'hourly'
      return 'daily'
    } catch {
      return '15min'
    }
  })

  const filterParams = computed(() => ({
    start_date: startDate.value,
    end_date: endDate.value,
    signal_ids: selectedSignalIds.value,
    approach: approach.value,
    valid_geometry: validGeometry.value,
    anomaly_type: anomalyType.value,
    // Only include time filter when different from defaults (for efficiency)
    start_hour: !isDefaultTimeRange.value ? startHour.value : undefined,
    start_minute: !isDefaultTimeRange.value ? startMinute.value : undefined,
    end_hour: !isDefaultTimeRange.value ? endHour.value : undefined,
    end_minute: !isDefaultTimeRange.value ? endMinute.value : undefined,
    day_of_week: dayOfWeek.value.length > 0 ? dayOfWeek.value : undefined
  }))

  // Actions
  function setDateRange(start, end) {
    startDate.value = start
    endDate.value = end
  }

  function setSelectedSignalIds(ids) {
    selectedSignalIds.value = ids
  }

  function setApproach(value) {
    approach.value = value
  }

  function setValidGeometry(value) {
    validGeometry.value = value
  }

  function setAnomalyType(value) {
    anomalyType.value = value
  }

  function setTimeOfDayRange(startH, startM, endH, endM) {
    startHour.value = startH
    startMinute.value = startM
    endHour.value = endH
    endMinute.value = endM
  }

  function setTimeFilterEnabled(enabled) {
    timeFilterEnabled.value = enabled
  }

  function setDayOfWeek(days) {
    dayOfWeek.value = days
  }

  // Initialize config values from backend
  async function initializeConfig() {
    try {
      const response = await fetch('/api/config')
      const config = await response.json()

      if (config.defaultStartHour !== undefined) {
        defaultStartHour.value = config.defaultStartHour
        startHour.value = config.defaultStartHour
      }
      if (config.defaultEndHour !== undefined) {
        defaultEndHour.value = config.defaultEndHour
        endHour.value = config.defaultEndHour
      }
    } catch (error) {
      console.error('Failed to load config:', error)
      // Keep default values on error
    }
  }

  return {
    // State
    startDate,
    endDate,
    selectedSignalIds,
    approach,
    validGeometry,
    anomalyType,
    startHour,
    startMinute,
    endHour,
    endMinute,
    timeFilterEnabled,
    dayOfWeek,
    defaultStartHour,
    defaultEndHour,

    // Computed
    hasSignalFilters,
    isDefaultTimeRange,
    aggregationLevel,
    filterParams,

    // Actions
    setDateRange,
    setSelectedSignalIds,
    setApproach,
    setValidGeometry,
    setAnomalyType,
    setTimeOfDayRange,
    setTimeFilterEnabled,
    setDayOfWeek,
    initializeConfig
  }
})