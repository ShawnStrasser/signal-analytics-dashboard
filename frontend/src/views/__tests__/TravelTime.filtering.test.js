/**
 * TravelTime View - Signal ID Filtering Tests
 * Tests for the Signal ID legend filtering logic
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useSelectionStore } from '@/stores/selection'
import { setupTestPinia, createMockSignal, createMockXdSegment } from '@/test-utils'

/**
 * This test file covers the Signal ID filtering logic implemented in TravelTime.vue
 *
 * Context: When legendBy is set to 'id' (Signal ID), the chart should:
 * 1. Show only selected signals when signals are clicked on the map
 * 2. Show signals associated with XD segments when XD segments are clicked directly
 *
 * The filtering logic identifies "orphan" XD segments (XDs selected but not belonging
 * to any selected signal) and includes their associated signals in the chart.
 */

describe('TravelTime View - Signal ID Filtering Logic', () => {
  let selectionStore

  beforeEach(() => {
    setupTestPinia()
    selectionStore = useSelectionStore()
  })

  describe('Orphan XD Detection', () => {
    beforeEach(() => {
      // Setup: Signal 1 has XD 100, 200; Signal 2 has XD 200, 300 (shared XD 200)
      const signals = [
        createMockSignal({ ID: '1' }),
        createMockSignal({ ID: '2' }),
      ]
      const xdSegments = [
        createMockXdSegment({ ID: '1', XD: 100 }),
        createMockXdSegment({ ID: '1', XD: 200 }),
        createMockXdSegment({ ID: '2', XD: 200 }),
        createMockXdSegment({ ID: '2', XD: 300 }),
      ]
      selectionStore.updateMappings(signals, xdSegments)
    })

    it('should identify orphan XD when XD is selected without its signal', () => {
      // Scenario: User clicks Signal 1, then clicks XD 300 (belongs to Signal 2)
      selectionStore.toggleSignal('1')
      selectionStore.toggleXdSegment(300)

      const selectedSignals = Array.from(selectionStore.selectedSignals)
      const selectedXds = Array.from(selectionStore.selectedXdSegments)

      // Signal 1 is selected, XD 100, 200, 300 are selected
      expect(selectedSignals).toEqual(['1'])
      expect(selectedXds.sort()).toEqual([100, 200, 300])

      // Orphan detection logic: XD 300 is orphan (not associated with Signal 1)
      const orphanXds = selectedXds.filter(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        const belongsToSelectedSignal = associatedSignals.some(sigId => selectedSignals.includes(sigId))
        return !belongsToSelectedSignal
      })

      expect(orphanXds).toEqual([300])
    })

    it('should not consider XD as orphan when it belongs to a selected signal', () => {
      // Scenario: User clicks Signal 1
      selectionStore.toggleSignal('1')

      const selectedSignals = Array.from(selectionStore.selectedSignals)
      const selectedXds = Array.from(selectionStore.selectedXdSegments)

      // Signal 1 is selected, XD 100, 200 are selected
      expect(selectedSignals).toEqual(['1'])
      expect(selectedXds.sort()).toEqual([100, 200])

      // Orphan detection: No orphans (all XDs belong to Signal 1)
      const orphanXds = selectedXds.filter(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        const belongsToSelectedSignal = associatedSignals.some(sigId => selectedSignals.includes(sigId))
        return !belongsToSelectedSignal
      })

      expect(orphanXds).toEqual([])
    })

    it('should handle shared XD correctly when parent signal is selected', () => {
      // Scenario: User clicks Signal 1 (which owns XD 200 shared with Signal 2)
      selectionStore.toggleSignal('1')

      const selectedSignals = Array.from(selectionStore.selectedSignals)
      const selectedXds = Array.from(selectionStore.selectedXdSegments)

      // XD 200 is shared but belongs to selected Signal 1, so not orphan
      const orphanXds = selectedXds.filter(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        const belongsToSelectedSignal = associatedSignals.some(sigId => selectedSignals.includes(sigId))
        return !belongsToSelectedSignal
      })

      expect(orphanXds).toEqual([])
    })
  })

  describe('Allowed Signals Calculation', () => {
    beforeEach(() => {
      // Setup: Signal 1 has XD 100, 200; Signal 2 has XD 200, 300; Signal 3 has XD 400
      const signals = [
        createMockSignal({ ID: '1' }),
        createMockSignal({ ID: '2' }),
        createMockSignal({ ID: '3' }),
      ]
      const xdSegments = [
        createMockXdSegment({ ID: '1', XD: 100 }),
        createMockXdSegment({ ID: '1', XD: 200 }),
        createMockXdSegment({ ID: '2', XD: 200 }),
        createMockXdSegment({ ID: '2', XD: 300 }),
        createMockXdSegment({ ID: '3', XD: 400 }),
      ]
      selectionStore.updateMappings(signals, xdSegments)
    })

    it('should allow only selected signals when no orphan XDs exist', () => {
      // Scenario: User clicks Signal 1
      selectionStore.toggleSignal('1')

      const selectedSignals = Array.from(selectionStore.selectedSignals)
      const selectedXds = Array.from(selectionStore.selectedXdSegments)

      // Build allowed signals set (mimics TravelTime.vue logic)
      const allowedSignals = new Set(selectedSignals)

      const orphanXds = selectedXds.filter(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        const belongsToSelectedSignal = associatedSignals.some(sigId => selectedSignals.includes(sigId))
        return !belongsToSelectedSignal
      })

      orphanXds.forEach(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        associatedSignals.forEach(sigId => allowedSignals.add(sigId))
      })

      expect(Array.from(allowedSignals)).toEqual(['1'])
    })

    it('should include signals from orphan XDs in allowed signals', () => {
      // Scenario: User clicks Signal 1, then clicks XD 300 (belongs to Signal 2)
      selectionStore.toggleSignal('1')
      selectionStore.toggleXdSegment(300)

      const selectedSignals = Array.from(selectionStore.selectedSignals)
      const selectedXds = Array.from(selectionStore.selectedXdSegments)

      // Build allowed signals set
      const allowedSignals = new Set(selectedSignals)

      const orphanXds = selectedXds.filter(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        const belongsToSelectedSignal = associatedSignals.some(sigId => selectedSignals.includes(sigId))
        return !belongsToSelectedSignal
      })

      orphanXds.forEach(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        associatedSignals.forEach(sigId => allowedSignals.add(sigId))
      })

      // Signal 1 (selected) + Signal 2 (from orphan XD 300)
      expect(Array.from(allowedSignals).sort()).toEqual(['1', '2'])
    })

    it('should handle multiple orphan XDs from different signals', () => {
      // Scenario: User clicks Signal 1, then clicks XD 300 and XD 400
      selectionStore.toggleSignal('1')
      selectionStore.toggleXdSegment(300)
      selectionStore.toggleXdSegment(400)

      const selectedSignals = Array.from(selectionStore.selectedSignals)
      const selectedXds = Array.from(selectionStore.selectedXdSegments)

      // Build allowed signals set
      const allowedSignals = new Set(selectedSignals)

      const orphanXds = selectedXds.filter(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        const belongsToSelectedSignal = associatedSignals.some(sigId => selectedSignals.includes(sigId))
        return !belongsToSelectedSignal
      })

      orphanXds.forEach(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        associatedSignals.forEach(sigId => allowedSignals.add(sigId))
      })

      // Signal 1 (selected) + Signal 2 (from XD 300) + Signal 3 (from XD 400)
      expect(Array.from(allowedSignals).sort()).toEqual(['1', '2', '3'])
    })
  })

  describe('Chart Data Filtering', () => {
    beforeEach(() => {
      // Setup: Signal 1 has XD 100, 200; Signal 2 has XD 200, 300
      const signals = [
        createMockSignal({ ID: '1' }),
        createMockSignal({ ID: '2' }),
      ]
      const xdSegments = [
        createMockXdSegment({ ID: '1', XD: 100 }),
        createMockXdSegment({ ID: '1', XD: 200 }),
        createMockXdSegment({ ID: '2', XD: 200 }),
        createMockXdSegment({ ID: '2', XD: 300 }),
      ]
      selectionStore.updateMappings(signals, xdSegments)
    })

    it('should filter chart data to only show selected signals', () => {
      // Scenario: User clicks Signal 1, chart should only show Signal 1 data
      selectionStore.toggleSignal('1')

      const selectedSignals = Array.from(selectionStore.selectedSignals)
      const selectedXds = Array.from(selectionStore.selectedXdSegments)

      // Simulate chart data with LEGEND_GROUP column
      const chartData = [
        { TIMESTAMP: '2024-01-01', TRAVEL_TIME_INDEX: 1.2, LEGEND_GROUP: '1' },
        { TIMESTAMP: '2024-01-01', TRAVEL_TIME_INDEX: 1.5, LEGEND_GROUP: '2' },
        { TIMESTAMP: '2024-01-02', TRAVEL_TIME_INDEX: 1.3, LEGEND_GROUP: '1' },
        { TIMESTAMP: '2024-01-02', TRAVEL_TIME_INDEX: 1.6, LEGEND_GROUP: '2' },
      ]

      // Build allowed signals set
      const allowedSignals = new Set(selectedSignals)

      const orphanXds = selectedXds.filter(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        const belongsToSelectedSignal = associatedSignals.some(sigId => selectedSignals.includes(sigId))
        return !belongsToSelectedSignal
      })

      orphanXds.forEach(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        associatedSignals.forEach(sigId => allowedSignals.add(sigId))
      })

      // Filter chart data
      const filteredData = chartData.filter(row => {
        const signalId = String(row.LEGEND_GROUP)
        return allowedSignals.has(signalId)
      })

      expect(filteredData.length).toBe(2) // Only Signal 1 data
      expect(filteredData.every(row => row.LEGEND_GROUP === '1')).toBe(true)
    })

    it('should include orphan signal data in filtered chart', () => {
      // Scenario: User clicks Signal 1, then clicks XD 300 (Signal 2)
      selectionStore.toggleSignal('1')
      selectionStore.toggleXdSegment(300)

      const selectedSignals = Array.from(selectionStore.selectedSignals)
      const selectedXds = Array.from(selectionStore.selectedXdSegments)

      const chartData = [
        { TIMESTAMP: '2024-01-01', TRAVEL_TIME_INDEX: 1.2, LEGEND_GROUP: '1' },
        { TIMESTAMP: '2024-01-01', TRAVEL_TIME_INDEX: 1.5, LEGEND_GROUP: '2' },
        { TIMESTAMP: '2024-01-02', TRAVEL_TIME_INDEX: 1.3, LEGEND_GROUP: '1' },
        { TIMESTAMP: '2024-01-02', TRAVEL_TIME_INDEX: 1.6, LEGEND_GROUP: '2' },
      ]

      // Build allowed signals set
      const allowedSignals = new Set(selectedSignals)

      const orphanXds = selectedXds.filter(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        const belongsToSelectedSignal = associatedSignals.some(sigId => selectedSignals.includes(sigId))
        return !belongsToSelectedSignal
      })

      orphanXds.forEach(xd => {
        const associatedSignals = selectionStore.getSignalsForXdSegment(xd)
        associatedSignals.forEach(sigId => allowedSignals.add(sigId))
      })

      // Filter chart data
      const filteredData = chartData.filter(row => {
        const signalId = String(row.LEGEND_GROUP)
        return allowedSignals.has(signalId)
      })

      expect(filteredData.length).toBe(4) // Both Signal 1 and Signal 2 data
      const uniqueSignals = new Set(filteredData.map(row => row.LEGEND_GROUP))
      expect(Array.from(uniqueSignals).sort()).toEqual(['1', '2'])
    })
  })
})
