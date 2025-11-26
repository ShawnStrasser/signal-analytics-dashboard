import { debugLog } from '@/config'
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import ApiService from '@/services/api'
import { useFiltersStore } from './filters'

export const useSignalsStore = defineStore('signals', () => {
  // State
  const dimSignals = ref([])  // Complete list from DIM_SIGNALS
  const loading = ref(false)
  const error = ref(null)

  // Actions
  async function loadDimSignals() {
    // Return early if already loaded
    if (dimSignals.value.length > 0) {
      return
    }

    loading.value = true
    error.value = null

    try {
      const arrowTable = await ApiService.getDimSignals()
      dimSignals.value = ApiService.arrowTableToObjects(arrowTable)
      debugLog(`📊 Loaded ${dimSignals.value.length} signals from DIM_SIGNALS`)
    } catch (err) {
      console.error('Failed to load DIM_SIGNALS:', err)
      error.value = err.message
      throw err
    } finally {
      loading.value = false
    }
  }

  // Computed: Filter signals by maintainedBy (client-side)
  const filteredSignals = computed(() => {
    const filtersStore = useFiltersStore()
    let filtered = dimSignals.value

    if (filtersStore.maintainedBy === 'odot') {
      filtered = filtered.filter(s => s.ODOT_MAINTAINED === true)
    } else if (filtersStore.maintainedBy === 'others') {
      filtered = filtered.filter(s => s.ODOT_MAINTAINED === false)
    }
    // If 'all', return all signals

    return filtered
  })

  // Computed: Group signals by district (for hierarchical UI)
  const signalsByDistrict = computed(() => {
    const grouped = {}

    filteredSignals.value.forEach(signal => {
      const district = signal.DISTRICT || 'Unknown'
      if (!grouped[district]) {
        grouped[district] = []
      }
      grouped[district].push(signal)
    })

    return grouped
  })

  // Computed: Get list of all districts
  const districts = computed(() => {
    return Object.keys(signalsByDistrict.value).sort()
  })

  // Computed: Get signal by ID (for quick lookups)
  const getSignalById = computed(() => {
    const signalMap = {}
    dimSignals.value.forEach(signal => {
      signalMap[signal.ID] = signal
    })
    return (id) => signalMap[id]
  })

  return {
    // State
    dimSignals,
    loading,
    error,

    // Computed
    filteredSignals,
    signalsByDistrict,
    districts,
    getSignalById,

    // Actions
    loadDimSignals
  }
})
