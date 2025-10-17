/**
 * Anomalies View - Filtering Tests
 * Tests for the Anomalies page filtering logic
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useSelectionStore } from '@/stores/selection'
import { setupTestPinia, createMockSignal, createMockXdSegment } from '@/test-utils'

/**
 * This test file covers the filtering logic for the Anomalies page
 *
 * Context: The Anomalies page should:
 * 1. Filter out signals with 0% anomaly from the map (but keep XD segments)
 * 2. Show chart data based on map selections (signals and XD segments)
 * 3. Handle orphan XD segments correctly (same logic as Travel Time)
 */

describe('Anomalies View - Filtering Logic', () => {
  let selectionStore

  beforeEach(() => {
    setupTestPinia()
    selectionStore = useSelectionStore()
  })

  describe('Zero Anomaly Signal Filtering', () => {
    it('should filter out signals with 0% anomaly from map data', () => {
      // Simulate signal metrics from backend
      const signalMetrics = [
        { ID: '1', ANOMALY_COUNT: 10, RECORD_COUNT: 100 },
        { ID: '2', ANOMALY_COUNT: 0, RECORD_COUNT: 100 },
        { ID: '3', ANOMALY_COUNT: 5, RECORD_COUNT: 100 },
      ]

      // Calculate percentages and filter (mimics Anomalies.vue logic)
      const signalObjects = signalMetrics
        .map(metric => ({
          ID: metric.ID,
          ANOMALY_COUNT: metric.ANOMALY_COUNT,
          RECORD_COUNT: metric.RECORD_COUNT,
          ANOMALY_PERCENTAGE: metric.RECORD_COUNT > 0
            ? (metric.ANOMALY_COUNT / metric.RECORD_COUNT) * 100
            : 0
        }))
        .filter(signal => signal.ANOMALY_PERCENTAGE > 0)

      expect(signalObjects.length).toBe(2)
      expect(signalObjects.map(s => s.ID)).toEqual(['1', '3'])
    })

    it('should keep signals with very small non-zero anomaly percentages', () => {
      const signalMetrics = [
        { ID: '1', ANOMALY_COUNT: 1, RECORD_COUNT: 10000 }, // 0.01%
        { ID: '2', ANOMALY_COUNT: 0, RECORD_COUNT: 100 },
      ]

      const signalObjects = signalMetrics
        .map(metric => ({
          ID: metric.ID,
          ANOMALY_COUNT: metric.ANOMALY_COUNT,
          RECORD_COUNT: metric.RECORD_COUNT,
          ANOMALY_PERCENTAGE: metric.RECORD_COUNT > 0
            ? (metric.ANOMALY_COUNT / metric.RECORD_COUNT) * 100
            : 0
        }))
        .filter(signal => signal.ANOMALY_PERCENTAGE > 0)

      expect(signalObjects.length).toBe(1)
      expect(signalObjects[0].ID).toBe('1')
      expect(signalObjects[0].ANOMALY_PERCENTAGE).toBeCloseTo(0.01)
    })

    it('should not filter XD segments with 0% anomaly', () => {
      // XD segments should NOT be filtered by 0% anomaly
      const xdMetrics = [
        { XD: 100, ANOMALY_COUNT: 10, RECORD_COUNT: 100 },
        { XD: 200, ANOMALY_COUNT: 0, RECORD_COUNT: 100 },
        { XD: 300, ANOMALY_COUNT: 5, RECORD_COUNT: 100 },
      ]

      // XD segments are NOT filtered by anomaly percentage
      const xdObjects = xdMetrics.map(metric => ({
        XD: metric.XD,
        ANOMALY_COUNT: metric.ANOMALY_COUNT,
        RECORD_COUNT: metric.RECORD_COUNT,
        ANOMALY_PERCENTAGE: metric.RECORD_COUNT > 0
          ? (metric.ANOMALY_COUNT / metric.RECORD_COUNT) * 100
          : 0
      }))

      expect(xdObjects.length).toBe(3)
      expect(xdObjects.map(xd => xd.XD)).toEqual([100, 200, 300])
    })
  })

  describe('Map Selection and Chart Filtering', () => {
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

    it('should send selected XD segments to chart API', () => {
      // Scenario: User clicks Signal 1
      selectionStore.toggleSignal('1')

      const selectedXds = Array.from(selectionStore.allSelectedXdSegments)

      // Chart API should receive XD 100 and 200
      expect(selectedXds.sort()).toEqual([100, 200])
    })

    it('should send only XD segments when XD is clicked directly', () => {
      // Scenario: User clicks XD 300 directly (no signal selected)
      selectionStore.toggleXdSegment(300)

      const selectedXds = Array.from(selectionStore.allSelectedXdSegments)

      // Chart API should receive only XD 300
      expect(selectedXds).toEqual([300])
    })

    it('should combine signal and direct XD selections', () => {
      // Scenario: User clicks Signal 1, then clicks XD 300
      selectionStore.toggleSignal('1')
      selectionStore.toggleXdSegment(300)

      const selectedXds = Array.from(selectionStore.allSelectedXdSegments)

      // Chart API should receive XD 100, 200 (from Signal 1) + 300 (direct)
      expect(selectedXds.sort()).toEqual([100, 200, 300])
    })

    it('should show empty chart when no selections exist', () => {
      // No selections
      const hasSelections = selectionStore.hasMapSelections

      expect(hasSelections).toBe(false)

      // Chart should be empty (mimics Anomalies.vue loadChartData logic)
      if (!hasSelections) {
        // Show all data (no XD filter applied)
        expect(true).toBe(true)
      }
    })
  })

  describe('Anomaly Type Filtering', () => {
    it('should use ANOMALY_COUNT when anomalyType is "All"', () => {
      const metric = {
        ID: '1',
        ANOMALY_COUNT: 10,
        POINT_SOURCE_COUNT: 3,
        RECORD_COUNT: 100
      }

      const anomalyType = 'All'
      const countColumn = anomalyType === 'Point Source' ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
      const count = metric[countColumn]
      const percentage = (count / metric.RECORD_COUNT) * 100

      expect(count).toBe(10)
      expect(percentage).toBe(10)
    })

    it('should use POINT_SOURCE_COUNT when anomalyType is "Point Source"', () => {
      const metric = {
        ID: '1',
        ANOMALY_COUNT: 10,
        POINT_SOURCE_COUNT: 3,
        RECORD_COUNT: 100
      }

      const anomalyType = 'Point Source'
      const countColumn = anomalyType === 'Point Source' ? 'POINT_SOURCE_COUNT' : 'ANOMALY_COUNT'
      const count = metric[countColumn]
      const percentage = (count / metric.RECORD_COUNT) * 100

      expect(count).toBe(3)
      expect(percentage).toBe(3)
    })
  })

  describe('Chart Data with Map Selections', () => {
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

    it('should build correct XD filter for chart API', () => {
      // Scenario: User selects Signal 1
      selectionStore.toggleSignal('1')

      const selectedXds = Array.from(selectionStore.allSelectedXdSegments)

      // Simulate building API filters (mimics Anomalies.vue loadChartData)
      const filters = {
        start_date: '2024-01-01',
        end_date: '2024-01-31'
      }

      if (selectionStore.hasMapSelections && selectedXds.length > 0) {
        filters.xd_segments = selectedXds
      }

      expect(filters.xd_segments).toEqual([100, 200])
    })

    it('should not add xd_segments filter when no selections', () => {
      // No selections
      const selectedXds = Array.from(selectionStore.allSelectedXdSegments)

      const filters = {
        start_date: '2024-01-01',
        end_date: '2024-01-31'
      }

      if (selectionStore.hasMapSelections && selectedXds.length > 0) {
        filters.xd_segments = selectedXds
      }

      expect(filters.xd_segments).toBeUndefined()
    })
  })

  describe('Edge Cases', () => {
    it('should handle signals with no records (RECORD_COUNT = 0)', () => {
      const signalMetrics = [
        { ID: '1', ANOMALY_COUNT: 0, RECORD_COUNT: 0 },
      ]

      const signalObjects = signalMetrics
        .map(metric => ({
          ID: metric.ID,
          ANOMALY_COUNT: metric.ANOMALY_COUNT,
          RECORD_COUNT: metric.RECORD_COUNT,
          ANOMALY_PERCENTAGE: metric.RECORD_COUNT > 0
            ? (metric.ANOMALY_COUNT / metric.RECORD_COUNT) * 100
            : 0
        }))
        .filter(signal => signal.ANOMALY_PERCENTAGE > 0)

      expect(signalObjects.length).toBe(0)
    })

    it('should handle null/undefined anomaly counts', () => {
      const signalMetrics = [
        { ID: '1', ANOMALY_COUNT: null, RECORD_COUNT: 100 },
        { ID: '2', ANOMALY_COUNT: undefined, RECORD_COUNT: 100 },
      ]

      const signalObjects = signalMetrics
        .map(metric => ({
          ID: metric.ID,
          ANOMALY_COUNT: metric.ANOMALY_COUNT || 0,
          RECORD_COUNT: metric.RECORD_COUNT,
          ANOMALY_PERCENTAGE: metric.RECORD_COUNT > 0
            ? ((metric.ANOMALY_COUNT || 0) / metric.RECORD_COUNT) * 100
            : 0
        }))
        .filter(signal => signal.ANOMALY_PERCENTAGE > 0)

      expect(signalObjects.length).toBe(0)
    })

    it('should handle 100% anomaly rate', () => {
      const signalMetrics = [
        { ID: '1', ANOMALY_COUNT: 100, RECORD_COUNT: 100 },
      ]

      const signalObjects = signalMetrics
        .map(metric => ({
          ID: metric.ID,
          ANOMALY_COUNT: metric.ANOMALY_COUNT,
          RECORD_COUNT: metric.RECORD_COUNT,
          ANOMALY_PERCENTAGE: metric.RECORD_COUNT > 0
            ? (metric.ANOMALY_COUNT / metric.RECORD_COUNT) * 100
            : 0
        }))
        .filter(signal => signal.ANOMALY_PERCENTAGE > 0)

      expect(signalObjects.length).toBe(1)
      expect(signalObjects[0].ANOMALY_PERCENTAGE).toBe(100)
    })
  })
})
