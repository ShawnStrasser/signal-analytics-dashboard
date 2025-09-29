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
  const selectedSignalFromMap = ref(null)

  // Computed
  const hasSignalFilters = computed(() => selectedSignalIds.value.length > 0)
  
  const filterParams = computed(() => ({
    start_date: startDate.value,
    end_date: endDate.value,
    signal_ids: selectedSignalIds.value,
    approach: approach.value,
    valid_geometry: validGeometry.value,
    anomaly_type: anomalyType.value
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

  function setSelectedSignalFromMap(signalId) {
    selectedSignalFromMap.value = signalId
  }

  function clearSelectedSignalFromMap() {
    selectedSignalFromMap.value = null
  }

  return {
    // State
    startDate,
    endDate,
    selectedSignalIds,
    approach,
    validGeometry,
    anomalyType,
    selectedSignalFromMap,
    
    // Computed
    hasSignalFilters,
    filterParams,
    
    // Actions
    setDateRange,
    setSelectedSignalIds,
    setApproach,
    setValidGeometry,
    setAnomalyType,
    setSelectedSignalFromMap,
    clearSelectedSignalFromMap
  }
})