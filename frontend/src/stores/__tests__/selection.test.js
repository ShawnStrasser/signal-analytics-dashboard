/**
 * Selection Store Unit Tests
 * Tests for map interaction selection logic
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useSelectionStore } from '../selection'
import { setupTestPinia, createMockSignal, createMockXdSegment, createMultiXdSignal, createOverlappingSignals } from '@/test-utils'

describe('Selection Store', () => {
  let store

  beforeEach(() => {
    setupTestPinia()
    store = useSelectionStore()
  })

  describe('Initial State', () => {
    it('should start with empty selections', () => {
      expect(store.selectedSignals.size).toBe(0)
      expect(store.selectedXdSegments.size).toBe(0)
      expect(store.hasMapSelections).toBe(false)
    })

    it('should have empty mappings', () => {
      expect(store.signalToXdMap.size).toBe(0)
      expect(store.xdToSignalsMap.size).toBe(0)
    })
  })

  describe('updateMappings', () => {
    it('should build signal-to-XD mappings', () => {
      // Note: Using XD segments with string IDs per VARCHAR schema
      const signals = [
        createMockXdSegment({ ID: '1', XD: 100 }),
        createMockXdSegment({ ID: '1', XD: 200 }),
        createMockXdSegment({ ID: '2', XD: 300 }),
      ]

      store.updateMappings(signals)

      expect(store.signalToXdMap.get('1')).toEqual([100, 200])
      expect(store.signalToXdMap.get('2')).toEqual([300])
    })

    it('should build XD-to-signals mappings', () => {
      const signals = [
        createMockXdSegment({ ID: '1', XD: 100 }),
        createMockXdSegment({ ID: '2', XD: 100 }), // Multiple signals share XD 100
        createMockXdSegment({ ID: '2', XD: 200 }),
      ]

      store.updateMappings(signals)

      expect(store.xdToSignalsMap.get(100)).toEqual(['1', '2'])
      expect(store.xdToSignalsMap.get(200)).toEqual(['2'])
    })

    it('should handle signals with null/undefined XD', () => {
      const signals = [
        createMockXdSegment({ ID: '1', XD: 100 }),
        createMockXdSegment({ ID: '2', XD: null }),
        createMockXdSegment({ ID: '3', XD: undefined }),
      ]

      store.updateMappings(signals)

      expect(store.signalToXdMap.size).toBe(1)
      expect(store.signalToXdMap.get('1')).toEqual([100])
      expect(store.signalToXdMap.has('2')).toBe(false)
      expect(store.signalToXdMap.has('3')).toBe(false)
    })

    it('should not duplicate XD segments for the same signal', () => {
      const signals = [
        createMockXdSegment({ ID: '1', XD: 100 }),
        createMockXdSegment({ ID: '1', XD: 100 }), // Duplicate
      ]

      store.updateMappings(signals)

      expect(store.signalToXdMap.get('1')).toEqual([100])
    })
  })

  describe('toggleSignal', () => {
    beforeEach(() => {
      // Setup: Signal 1 has XD segments 100 and 200
      const signals = createMultiXdSignal(1, [100, 200])
      store.updateMappings(signals)
    })

    it('should select signal and add all its XD segments', () => {
      store.toggleSignal('1')

      expect(store.isSignalSelected('1')).toBe(true)
      expect(store.selectedXdSegments.has(100)).toBe(true)
      expect(store.selectedXdSegments.has(200)).toBe(true)
      expect(store.hasMapSelections).toBe(true)
    })

    it('should deselect signal and remove all its XD segments', () => {
      // Select then deselect
      store.toggleSignal('1')
      store.toggleSignal('1')

      expect(store.isSignalSelected('1')).toBe(false)
      expect(store.selectedXdSegments.has(100)).toBe(false)
      expect(store.selectedXdSegments.has(200)).toBe(false)
      expect(store.hasMapSelections).toBe(false)
    })

    it('should handle multiple signal selections', () => {
      const signals = [
        ...createMultiXdSignal(1, [100, 200]),
        ...createMultiXdSignal(2, [300, 400]),
      ]
      store.updateMappings(signals)

      store.toggleSignal('1')
      store.toggleSignal('2')

      expect(store.selectedSignals.size).toBe(2)
      expect(store.selectedXdSegments.size).toBe(4)
      expect(Array.from(store.allSelectedXdSegments)).toEqual(
        expect.arrayContaining([100, 200, 300, 400])
      )
    })
  })

  describe('toggleXdSegment', () => {
    it('should toggle XD segment independently', () => {
      store.toggleXdSegment(100)

      expect(store.isXdSegmentSelected(100)).toBe(true)
      expect(store.hasMapSelections).toBe(true)
    })

    it('should deselect XD segment when toggled again', () => {
      store.toggleXdSegment(100)
      store.toggleXdSegment(100)

      expect(store.isXdSegmentSelected(100)).toBe(false)
      expect(store.hasMapSelections).toBe(false)
    })

    it('should allow XD selection independent of signal selection', () => {
      const signals = createMultiXdSignal(1, [100, 200])
      store.updateMappings(signals)

      // Select just the XD segment, not the signal
      store.toggleXdSegment(100)

      expect(store.isXdSegmentSelected(100)).toBe(true)
      expect(store.isSignalSelected('1')).toBe(false)
      expect(store.allSelectedXdSegments.has(100)).toBe(true)
    })
  })

  describe('Issue 1: Chart not updating when XD segment is deselected', () => {
    it('should remove XD from selectedXdSegmentsList when manually deselected', () => {
      // Setup: Signal 1 has XD 100, 200
      const signals = createMultiXdSignal(1, [100, 200])
      store.updateMappings(signals)

      // Step 1: Select signal (chart shows XD 100, 200)
      store.toggleSignal('1')
      expect(store.selectedXdSegmentsList.sort()).toEqual([100, 200])

      // Step 2: Click on XD 100 to deselect it
      store.toggleXdSegment(100)

      // EXPECTED: Chart should only show XD 200
      // BUG: Chart still shows XD 100, 200 because allSelectedXdSegments
      // includes XD from selected signals even if manually deselected
      expect(store.selectedXdSegmentsList).toEqual([200])
    })
  })

  describe('Issue 4: Shared XD Segments Incorrectly Deselected', () => {
    it('should keep shared XD segment selected when one signal is deselected but another is still selected', () => {
      // Signal 1: XD 100, 200
      // Signal 2: XD 200, 300 (XD 200 is shared)
      const signals = [
        createMockXdSegment({ ID: '1', XD: 100 }),
        createMockXdSegment({ ID: '1', XD: 200 }),
        createMockXdSegment({ ID: '2', XD: 200 }),
        createMockXdSegment({ ID: '2', XD: 300 }),
      ]
      store.updateMappings(signals)

      // Select both signals
      store.toggleSignal('1')
      store.toggleSignal('2')

      expect(store.selectedXdSegmentsList.sort()).toEqual([100, 200, 300])

      // Deselect signal 1
      store.toggleSignal('1')

      // EXPECTED: XD 200 should still be selected (because signal 2 is still selected)
      // BUG: XD 200 gets deselected even though signal 2 is still selected
      expect(store.isXdSegmentSelected(200)).toBe(true)
      expect(store.isXdSegmentSelected(100)).toBe(false)
      expect(store.isXdSegmentSelected(300)).toBe(true)
    })
  })

  describe('allSelectedXdSegments computed property', () => {
    beforeEach(() => {
      const signals = createMultiXdSignal(1, [100, 200])
      store.updateMappings(signals)
    })

    it('should include XD segments from selected signals', () => {
      store.toggleSignal('1')

      expect(store.allSelectedXdSegments.has(100)).toBe(true)
      expect(store.allSelectedXdSegments.has(200)).toBe(true)
    })

    it('should include directly selected XD segments', () => {
      store.toggleXdSegment(999)

      expect(store.allSelectedXdSegments.has(999)).toBe(true)
    })

    it('should combine signal-based and direct XD selections', () => {
      store.toggleSignal('1') // Adds XD 100, 200
      store.toggleXdSegment(999) // Adds XD 999 directly

      expect(store.allSelectedXdSegments.size).toBe(3)
      expect(Array.from(store.allSelectedXdSegments).sort()).toEqual([100, 200, 999])
    })

    it('should deselect XD segment when toggled if already selected', () => {
      store.toggleSignal('1') // Adds XD 100, 200
      store.toggleXdSegment(100) // XD 100 already in selection from signal, so toggle removes it

      // XD 100 should now be deselected (toggle behavior)
      const allXds = Array.from(store.allSelectedXdSegments)
      expect(allXds.includes(100)).toBe(false)
      expect(allXds.includes(200)).toBe(true)
      expect(store.allSelectedXdSegments.size).toBe(1)
    })
  })

  describe('hasMapSelections computed property', () => {
    it('should be true when signals are selected', () => {
      const signals = createMultiXdSignal(1, [100])
      store.updateMappings(signals)
      store.toggleSignal('1')

      expect(store.hasMapSelections).toBe(true)
    })

    it('should be true when XD segments are selected', () => {
      store.toggleXdSegment(100)

      expect(store.hasMapSelections).toBe(true)
    })

    it('should be false when nothing is selected', () => {
      expect(store.hasMapSelections).toBe(false)
    })

    it('should be false after clearing all selections', () => {
      store.toggleXdSegment(100)
      store.clearAllSelections()

      expect(store.hasMapSelections).toBe(false)
    })
  })

  describe('clearAllSelections', () => {
    it('should clear all signals and XD segments', () => {
      const signals = createMultiXdSignal(1, [100, 200])
      store.updateMappings(signals)
      store.toggleSignal('1')
      store.toggleXdSegment(999)

      store.clearAllSelections()

      expect(store.selectedSignals.size).toBe(0)
      expect(store.selectedXdSegments.size).toBe(0)
      expect(store.hasMapSelections).toBe(false)
    })
  })

  describe('Helper Methods', () => {
    beforeEach(() => {
      const signals = createOverlappingSignals()
      store.updateMappings(signals)
    })

    it('isSignalSelected should return correct status', () => {
      expect(store.isSignalSelected('1')).toBe(false)

      store.toggleSignal('1')
      expect(store.isSignalSelected('1')).toBe(true)
    })

    it('isXdSegmentSelected should return correct status', () => {
      expect(store.isXdSegmentSelected(100)).toBe(false)

      store.toggleXdSegment(100)
      expect(store.isXdSegmentSelected(100)).toBe(true)
    })

    it('getSignalsForXdSegment should return associated signals', () => {
      // Note: IDs are now VARCHAR strings per README.md schema
      expect(store.getSignalsForXdSegment(200)).toEqual(['1', '2']) // Shared by signals 1 and 2
      expect(store.getSignalsForXdSegment(100)).toEqual(['1'])
      expect(store.getSignalsForXdSegment(400)).toEqual(['3'])
    })

    it('getXdSegmentsForSignal should return associated XD segments', () => {
      // Note: IDs are now VARCHAR strings per README.md schema
      expect(store.getXdSegmentsForSignal('1')).toEqual([100, 200])
      expect(store.getXdSegmentsForSignal('2')).toEqual([200, 300])
      expect(store.getXdSegmentsForSignal('3')).toEqual([400])
    })
  })

  describe('Array Versions (for iteration)', () => {
    it('selectedSignalsList should return array of selected signals', () => {
      const signals = createMultiXdSignal(1, [100])
      store.updateMappings(signals)
      store.toggleSignal('1')

      expect(store.selectedSignalsList).toEqual(['1'])
    })

    it('selectedXdSegmentsList should return array of all selected XD segments', () => {
      const signals = createMultiXdSignal(1, [100, 200])
      store.updateMappings(signals)
      store.toggleSignal('1')
      store.toggleXdSegment(999)

      expect(store.selectedXdSegmentsList.sort()).toEqual([100, 200, 999])
    })
  })

  describe('Edge Cases', () => {
    it('should handle toggling signal with no XD mappings', () => {
      // Toggle signal that hasn't been mapped
      store.toggleSignal('999')

      expect(store.isSignalSelected('999')).toBe(true)
      expect(store.selectedXdSegments.size).toBe(0) // No XD segments added
    })

    it('should handle empty signals array', () => {
      store.updateMappings([])

      expect(store.signalToXdMap.size).toBe(0)
      expect(store.xdToSignalsMap.size).toBe(0)
    })

    it('should allow re-selecting the same XD segment after signal deselection', () => {
      const signals = createMultiXdSignal(1, [100])
      store.updateMappings(signals)

      // Select signal (adds XD 100)
      store.toggleSignal('1')
      expect(store.selectedXdSegments.has(100)).toBe(true)

      // Deselect signal (removes XD 100)
      store.toggleSignal('1')
      expect(store.selectedXdSegments.has(100)).toBe(false)

      // Manually select XD 100 again
      store.toggleXdSegment(100)
      expect(store.selectedXdSegments.has(100)).toBe(true)
    })
  })
})
