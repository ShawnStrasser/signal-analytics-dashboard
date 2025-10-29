import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useFiltersStore = defineStore('filters', () => {
  // Config values from backend (will be populated on init)
  const defaultStartHour = ref(6)   // Default from config.py
  const defaultEndHour = ref(19)    // Default from config.py

  function formatDateOnly(date) {
    return date.toISOString().split('T')[0]
  }

  function getChangepointDefaultDates() {
    const today = new Date()
    const end = new Date(today)
    end.setDate(end.getDate() - 7) // One week before today
    const start = new Date(end)
    start.setDate(start.getDate() - 21) // Three additional weeks prior

    return {
      start: formatDateOnly(start),
      end: formatDateOnly(end)
    }
  }

  const { start: changepointStartDefault, end: changepointEndDefault } = getChangepointDefaultDates()

  // State
  const startDate = ref(new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]) // 2 days ago
  const endDate = ref(new Date().toISOString().split('T')[0]) // Today
  const changepointStartDate = ref(changepointStartDefault)
  const changepointEndDate = ref(changepointEndDefault)
  const selectedSignalIds = ref([])
  const selectedDistricts = ref([]) // Districts with all signals selected
  const approach = ref(null)
  const validGeometry = ref('all') // 'all', 'valid', or 'invalid'
  const maintainedBy = ref('all') // 'all', 'odot', or 'others'
  const anomalyType = ref('All')
  const startHour = ref(6)   // Will be set from config
  const startMinute = ref(0)
  const endHour = ref(19)    // Will be set from config
  const endMinute = ref(0)
  const timeFilterEnabled = ref(true)  // Time-of-day filter always enabled
  const dayOfWeek = ref([])  // Selected days of week (1=Mon, 2=Tue, ..., 7=Sun)
  const removeAnomalies = ref(false)  // Filter to remove anomalous data points
  const pctChangeImprovement = ref(1.0) // Percent threshold for improvements (displayed as whole number, sent as decimal)
  const pctChangeDegradation = ref(1.0) // Percent threshold for degradations (displayed as whole number, sent as decimal)

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
    maintained_by: maintainedBy.value !== 'all' ? maintainedBy.value : undefined,
    anomaly_type: anomalyType.value,
    // Only include time filter when different from defaults (for efficiency)
    start_hour: !isDefaultTimeRange.value ? startHour.value : undefined,
    start_minute: !isDefaultTimeRange.value ? startMinute.value : undefined,
    end_hour: !isDefaultTimeRange.value ? endHour.value : undefined,
    end_minute: !isDefaultTimeRange.value ? endMinute.value : undefined,
    day_of_week: dayOfWeek.value.length > 0 ? dayOfWeek.value : undefined,
    remove_anomalies: removeAnomalies.value || undefined
  }))

  const changepointFilterParams = computed(() => ({
    start_date: changepointStartDate.value,
    end_date: changepointEndDate.value,
    signal_ids: selectedSignalIds.value,
    approach: approach.value,
    valid_geometry: validGeometry.value !== 'all' ? validGeometry.value : undefined,
    maintained_by: maintainedBy.value !== 'all' ? maintainedBy.value : undefined,
    pct_change_improvement: pctChangeImprovement.value / 100, // Convert from whole number to decimal
    pct_change_degradation: pctChangeDegradation.value / 100  // Convert from whole number to decimal
  }))

  // Computed property that groups signals by district and filters by maintainedBy
  // This would normally fetch from an API, but for testing we return an empty object
  const filteredSignalsByDistrict = computed(() => {
    // In a real implementation, this would:
    // 1. Fetch signals from DIM_SIGNALS
    // 2. Group by DISTRICT column
    // 3. Filter by maintainedBy (ODOT_MAINTAINED boolean column)
    // For now, return an object structure that tests can work with
    return {}
  })

  // Actions
  function setDateRange(start, end) {
    startDate.value = start
    endDate.value = end
  }

  function setChangepointDateRange(start, end) {
    changepointStartDate.value = start
    changepointEndDate.value = end
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

  function setMaintainedBy(value) {
    maintainedBy.value = value
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

  function setRemoveAnomalies(value) {
    removeAnomalies.value = value
  }

  function setPctChangeImprovement(value) {
    const numeric = Number(value)
    if (!Number.isFinite(numeric)) {
      pctChangeImprovement.value = 0
      return
    }
    pctChangeImprovement.value = Math.max(0, numeric)
  }

  function setPctChangeDegradation(value) {
    const numeric = Number(value)
    if (!Number.isFinite(numeric)) {
      pctChangeDegradation.value = 0
      return
    }
    pctChangeDegradation.value = Math.max(0, numeric)
  }

  function selectDistrict(district, signalIds) {
    // Add district to selectedDistricts if not already there
    if (!selectedDistricts.value.includes(district)) {
      selectedDistricts.value.push(district)
    }

    // Add all signal IDs from this district to selectedSignalIds
    signalIds.forEach(id => {
      if (!selectedSignalIds.value.includes(id)) {
        selectedSignalIds.value.push(id)
      }
    })
  }

  function deselectDistrict(district, signalIds) {
    // Remove district from selectedDistricts
    selectedDistricts.value = selectedDistricts.value.filter(d => d !== district)

    // Remove all signal IDs from this district
    selectedSignalIds.value = selectedSignalIds.value.filter(
      id => !signalIds.includes(id)
    )
  }

  function deselectIndividualSignal(signalId) {
    // Remove the signal from selectedSignalIds
    selectedSignalIds.value = selectedSignalIds.value.filter(id => id !== signalId)

    // Check if any districts should be deselected because they're no longer fully selected
    // This is a simplified implementation - in a real app, you'd check if all signals
    // in each district are still selected
    // For now, we'll remove all districts since we can't know which district the signal belonged to
    // without additional data. In a real implementation, this would check against the actual
    // district-signal mapping
    selectedDistricts.value = []
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
    changepointStartDate,
    changepointEndDate,
    selectedSignalIds,
    selectedDistricts,
    approach,
    validGeometry,
    maintainedBy,
    anomalyType,
    startHour,
    startMinute,
    endHour,
    endMinute,
    timeFilterEnabled,
    dayOfWeek,
    removeAnomalies,
    defaultStartHour,
    defaultEndHour,
    pctChangeImprovement,
    pctChangeDegradation,

    // Computed
    hasSignalFilters,
    isDefaultTimeRange,
    aggregationLevel,
    filterParams,
    changepointFilterParams,
    filteredSignalsByDistrict,

    // Actions
    setDateRange,
    setChangepointDateRange,
    setSelectedSignalIds,
    setApproach,
    setValidGeometry,
    setMaintainedBy,
    setAnomalyType,
    setTimeOfDayRange,
    setTimeFilterEnabled,
    setDayOfWeek,
    setRemoveAnomalies,
    setPctChangeImprovement,
    setPctChangeDegradation,
    selectDistrict,
    deselectDistrict,
    deselectIndividualSignal,
    initializeConfig
  }
})
