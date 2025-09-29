import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useSelectionStore = defineStore('selection', () => {
  // State
  const selectedSignalsList = ref([])
  const selectedXdSegmentsList = ref([])
  const signalToXdMap = ref(new Map()) // Map signal ID to XD segments
  const xdToSignalsMap = ref(new Map()) // Map XD segment to signal IDs

  // Computed
  const hasMapSelections = computed(() => {
    return selectedSignalsList.value.length > 0 || selectedXdSegmentsList.value.length > 0
  })

  // Actions
  function updateMappings(signals) {
    // Build bidirectional mappings between signals and XD segments
    const sigToXd = new Map()
    const xdToSigs = new Map()

    signals.forEach(signal => {
      const signalId = signal.ID
      const xd = signal.XD

      if (signalId && xd !== undefined && xd !== null) {
        // Signal to XD mapping
        if (!sigToXd.has(signalId)) {
          sigToXd.set(signalId, [])
        }
        if (!sigToXd.get(signalId).includes(xd)) {
          sigToXd.get(signalId).push(xd)
        }

        // XD to signals mapping
        if (!xdToSigs.has(xd)) {
          xdToSigs.set(xd, [])
        }
        if (!xdToSigs.get(xd).includes(signalId)) {
          xdToSigs.get(xd).push(signalId)
        }
      }
    })

    signalToXdMap.value = sigToXd
    xdToSignalsMap.value = xdToSigs
  }

  function toggleSignal(signalId) {
    const index = selectedSignalsList.value.indexOf(signalId)
    if (index > -1) {
      selectedSignalsList.value.splice(index, 1)
    } else {
      selectedSignalsList.value.push(signalId)
    }
  }

  function toggleXdSegment(xdSegment) {
    const index = selectedXdSegmentsList.value.indexOf(xdSegment)
    if (index > -1) {
      selectedXdSegmentsList.value.splice(index, 1)
    } else {
      selectedXdSegmentsList.value.push(xdSegment)
    }
  }

  function isSignalSelected(signalId) {
    return selectedSignalsList.value.includes(signalId)
  }

  function isXdSegmentSelected(xdSegment) {
    return selectedXdSegmentsList.value.includes(xdSegment)
  }

  function getSignalsForXdSegment(xdSegment) {
    return xdToSignalsMap.value.get(xdSegment) || []
  }

  function getXdSegmentsForSignal(signalId) {
    return signalToXdMap.value.get(signalId) || []
  }

  function clearAllSelections() {
    selectedSignalsList.value = []
    selectedXdSegmentsList.value = []
  }

  return {
    // State
    selectedSignalsList,
    selectedXdSegmentsList,
    signalToXdMap,
    xdToSignalsMap,
    
    // Computed
    hasMapSelections,
    
    // Actions
    updateMappings,
    toggleSignal,
    toggleXdSegment,
    isSignalSelected,
    isXdSegmentSelected,
    getSignalsForXdSegment,
    getXdSegmentsForSignal,
    clearAllSelections
  }
})
