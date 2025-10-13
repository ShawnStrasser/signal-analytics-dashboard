import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useSelectionStore = defineStore('selection', () => {
  // State - track selected signals and XD segments separately
  const selectedSignals = ref(new Set())
  const selectedXdSegments = ref(new Set())
  const signalToXdMap = ref(new Map()) // Map signal ID to XD segments
  const xdToSignalsMap = ref(new Map()) // Map XD segment to signal IDs

  // Computed - check if there are any map selections
  const hasMapSelections = computed(() => {
    return selectedSignals.value.size > 0 || selectedXdSegments.value.size > 0
  })

  // Computed - get all XD segments that should be highlighted (from selected signals + directly selected)
  const allSelectedXdSegments = computed(() => {
    // Return only the XD segments in selectedXdSegments
    // This set is managed by toggleSignal and toggleXdSegment
    return new Set(selectedXdSegments.value)
  })

  // Computed - get array versions for easier iteration
  const selectedSignalsList = computed(() => Array.from(selectedSignals.value))
  const selectedXdSegmentsList = computed(() => Array.from(allSelectedXdSegments.value))

  // Actions
  function updateMappings(signals, xdSegments = null) {
    // Build bidirectional mappings between signals and XD segments
    const sigToXd = new Map()
    const xdToSigs = new Map()

    // For backward compatibility, check if signals have XD field (anomaly mode)
    const hasXdInSignals = signals.length > 0 && signals[0].XD !== undefined

    if (hasXdInSignals) {
      // Legacy path: signals contain XD field (anomaly mode)
      signals.forEach(signal => {
        const signalId = signal.ID
        const xd = signal.XD

        if (signalId && xd !== undefined && xd !== null) {
          // Signal to XD mapping (one signal can have multiple XD segments)
          if (!sigToXd.has(signalId)) {
            sigToXd.set(signalId, [])
          }
          if (!sigToXd.get(signalId).includes(xd)) {
            sigToXd.get(signalId).push(xd)
          }

          // XD to signals mapping (one XD can belong to multiple signals)
          if (!xdToSigs.has(xd)) {
            xdToSigs.set(xd, [])
          }
          if (!xdToSigs.get(xd).includes(signalId)) {
            xdToSigs.get(xd).push(signalId)
          }
        }
      })
    } else if (xdSegments && xdSegments.length > 0) {
      // New path: use separate xdSegments data (travel-time mode)
      // Build signal ID set for quick lookup
      const signalIds = new Set(signals.map(s => s.ID))

      xdSegments.forEach(xdSeg => {
        const xd = xdSeg.XD
        const signalId = xdSeg.ID

        if (signalId && xd !== undefined && xd !== null && signalIds.has(signalId)) {
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
    }

    signalToXdMap.value = sigToXd
    xdToSignalsMap.value = xdToSigs
  }

  function toggleSignal(signalId) {
    if (selectedSignals.value.has(signalId)) {
      // Deselecting a signal - only remove XD segments that aren't part of other selected signals
      selectedSignals.value.delete(signalId)
      const xdSegments = signalToXdMap.value.get(signalId) || []
      xdSegments.forEach(xd => {
        // Check if this XD segment belongs to any other selected signal
        const associatedSignals = xdToSignalsMap.value.get(xd) || []
        const isPartOfOtherSelectedSignal = associatedSignals.some(sigId =>
          sigId !== signalId && selectedSignals.value.has(sigId)
        )

        // Only remove if it's not part of another selected signal
        if (!isPartOfOtherSelectedSignal) {
          selectedXdSegments.value.delete(xd)
        }
      })
    } else {
      // Selecting a signal - toggle on all its XD segments
      selectedSignals.value.add(signalId)
      const xdSegments = signalToXdMap.value.get(signalId) || []
      xdSegments.forEach(xd => {
        selectedXdSegments.value.add(xd)
      })
    }
  }

  function toggleXdSegment(xdSegment) {
    if (selectedXdSegments.value.has(xdSegment)) {
      selectedXdSegments.value.delete(xdSegment)
    } else {
      selectedXdSegments.value.add(xdSegment)
    }
  }

  function isSignalSelected(signalId) {
    return selectedSignals.value.has(signalId)
  }

  function isXdSegmentSelected(xdSegment) {
    // An XD segment is "selected" only if it's in the selectedXdSegments set
    return selectedXdSegments.value.has(xdSegment)
  }

  function isXdSegmentDirectlySelected(xdSegment) {
    // Check if XD segment was clicked directly (not just via signal selection)
    return selectedXdSegments.value.has(xdSegment)
  }

  function getSignalsForXdSegment(xdSegment) {
    return xdToSignalsMap.value.get(xdSegment) || []
  }

  function getXdSegmentsForSignal(signalId) {
    return signalToXdMap.value.get(signalId) || []
  }

  function clearAllSelections() {
    selectedSignals.value.clear()
    selectedXdSegments.value.clear()
  }

  function setXdSegmentSelection(xdSegments) {
    // Set XD segments from an array (used by lasso selection)
    selectedXdSegments.value.clear()
    xdSegments.forEach(xd => selectedXdSegments.value.add(xd))
  }

  function clearXdSegmentSelection() {
    selectedXdSegments.value.clear()
  }

  return {
    // State
    selectedSignals,
    selectedXdSegments,
    signalToXdMap,
    xdToSignalsMap,

    // Computed
    hasMapSelections,
    allSelectedXdSegments,
    selectedSignalsList,
    selectedXdSegmentsList,

    // Actions
    updateMappings,
    toggleSignal,
    toggleXdSegment,
    isSignalSelected,
    isXdSegmentSelected,
    isXdSegmentDirectlySelected,
    getSignalsForXdSegment,
    getXdSegmentsForSignal,
    clearAllSelections,
    setXdSegmentSelection,
    clearXdSegmentSelection
  }
})
