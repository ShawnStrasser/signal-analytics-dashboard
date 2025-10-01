import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useFiltersStore = defineStore('filters', () => {
  // State
  const startDate = ref(new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]) // 2 days ago
  const endDate = ref(new Date().toISOString().split('T')[0]) // Today
  const selectedSignalIds = ref([])
  const approach = ref(null)
  const validGeometry = ref('all') // 'all', 'valid', or 'invalid'
  const anomalyType = ref('All')
  const startHour = ref(0)   // 00:00
  const endHour = ref(23)    // 23:00
  const timeFilterEnabled = ref(false)  // Whether time-of-day filter is active

  // Computed
  const hasSignalFilters = computed(() => selectedSignalIds.value.length > 0)

  const allDaySelected = computed(() => startHour.value === 0 && endHour.value === 23)

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
    start_hour: timeFilterEnabled.value ? startHour.value : undefined,
    end_hour: timeFilterEnabled.value ? endHour.value : undefined
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

  function setTimeOfDayRange(start, end) {
    startHour.value = start
    endHour.value = end
  }

  function setTimeFilterEnabled(enabled) {
    timeFilterEnabled.value = enabled
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
    endHour,
    timeFilterEnabled,

    // Computed
    hasSignalFilters,
    allDaySelected,
    aggregationLevel,
    filterParams,

    // Actions
    setDateRange,
    setSelectedSignalIds,
    setApproach,
    setValidGeometry,
    setAnomalyType,
    setTimeOfDayRange,
    setTimeFilterEnabled
  }
})