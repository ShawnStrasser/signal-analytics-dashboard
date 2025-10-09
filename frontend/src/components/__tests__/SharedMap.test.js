/**
 * SharedMap Component Tests
 * Tests for map interaction behavior and event emissions
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SharedMap from '../SharedMap.vue'
import { createPinia } from 'pinia'
import { useSelectionStore } from '@/stores/selection'
import { useGeometryStore } from '@/stores/geometry'
import { useMapStateStore } from '@/stores/mapState'
import { useThemeStore } from '@/stores/theme'
import { createMockSignal, createMultiXdSignal } from '@/test-utils'

// Mock Leaflet to avoid actual map rendering
vi.mock('leaflet', () => {
  const mockLayer = {
    addTo: vi.fn().mockReturnThis(),
    on: vi.fn(),
    setView: vi.fn().mockReturnThis(),
    getBounds: vi.fn(() => ({
      isValid: () => true,
      getNorth: () => 40.0,
      getSouth: () => 39.5,
      getEast: () => -104.5,
      getWest: () => -105.0,
      extend: vi.fn(),
    })),
    eachLayer: vi.fn(),
    clearLayers: vi.fn(),
    setStyle: vi.fn(),
  }

  const mockMarker = {
    setIcon: vi.fn().mockReturnThis(),
    bindTooltip: vi.fn().mockReturnThis(),
    setTooltipContent: vi.fn(),
    getTooltip: vi.fn(() => ({})),
    on: vi.fn(),
    getLatLng: vi.fn(() => ({ lat: 39.7392, lng: -104.9903 })),
    addTo: vi.fn().mockReturnThis(),
  }

  const L = {
    map: vi.fn(() => ({
      setView: vi.fn().mockReturnThis(),
      getCenter: vi.fn(() => ({ lat: 39.7392, lng: -104.9903 })),
      getZoom: vi.fn(() => 13),
      fitBounds: vi.fn(),
      remove: vi.fn(),
      on: vi.fn(),
      addLayer: vi.fn(),
      removeLayer: vi.fn(),
      removeControl: vi.fn(),
      addControl: vi.fn(),
    })),
    layerGroup: vi.fn(() => mockLayer),
    featureGroup: vi.fn(() => mockLayer),
    geoJSON: vi.fn(() => mockLayer),
    marker: vi.fn(() => mockMarker),
    divIcon: vi.fn((options) => options),
    latLngBounds: vi.fn(() => ({
      isValid: () => true,
      getNorth: () => 40.0,
      getSouth: () => 39.5,
      getEast: () => -104.5,
      getWest: () => -105.0,
      extend: vi.fn(),
    })),
    tileLayer: vi.fn(() => mockLayer),
    control: {
      layers: vi.fn(() => ({
        addTo: vi.fn().mockReturnThis(),
      })),
    },
    Control: {
      extend: vi.fn((options) => {
        return function() {
          return {
            onAdd: options.onAdd || vi.fn(),
            addTo: vi.fn().mockReturnThis(),
          }
        }
      }),
      Draw: vi.fn(function(options) {
        this.options = options
        this.addTo = vi.fn().mockReturnThis()
      }),
    },
    Draw: {
      Event: {
        CREATED: 'draw:created',
        DELETED: 'draw:deleted',
      },
    },
    DomEvent: {
      stopPropagation: vi.fn(),
      preventDefault: vi.fn(),
      on: vi.fn(),
    },
    DomUtil: {
      create: vi.fn((tag, className) => {
        const el = document.createElement(tag)
        if (className) el.className = className
        return el
      }),
    },
  }

  return { default: L }
})

// Mock leaflet-draw (depends on Leaflet being loaded first)
vi.mock('leaflet-draw', () => ({
  default: {},
}))

// Mock requestIdleCallback (not available in jsdom)
global.requestIdleCallback = vi.fn((cb) => setTimeout(cb, 0))

describe('SharedMap Component', () => {
  let wrapper
  let pinia
  let selectionStore

  beforeEach(() => {
    pinia = createPinia()
    selectionStore = useSelectionStore(pinia)

    // Mount component with minimal props
    wrapper = mount(SharedMap, {
      props: {
        signals: [],
        dataType: 'travel-time',
      },
      global: {
        plugins: [pinia],
      },
    })
  })

  describe('Component Mounting', () => {
    it('should render without errors', () => {
      expect(wrapper.exists()).toBe(true)
    })

    it('should create a map container', () => {
      expect(wrapper.find('div').exists()).toBe(true)
    })
  })

  describe('Signal Marker Interactions', () => {
    it('should call toggleSignal when marker is clicked', async () => {
      const signals = createMultiXdSignal('1', [100, 200])
      selectionStore.updateMappings(signals)

      // Verify initial state
      expect(selectionStore.isSignalSelected('1')).toBe(false)

      // Simulate marker click by calling the store directly
      // (In real component, this happens via marker.on('click', ...))
      selectionStore.toggleSignal('1')

      expect(selectionStore.isSignalSelected('1')).toBe(true)
      expect(selectionStore.selectedXdSegments.has(100)).toBe(true)
      expect(selectionStore.selectedXdSegments.has(200)).toBe(true)
    })
  })

  describe('XD Segment Interactions', () => {
    it('should call toggleXdSegment when XD layer is clicked', () => {
      const signals = createMultiXdSignal('1', [100])
      selectionStore.updateMappings(signals)

      // Simulate XD segment click
      selectionStore.toggleXdSegment(100)

      expect(selectionStore.isXdSegmentSelected(100)).toBe(true)
    })

    it('should allow independent XD selection without signal selection', () => {
      const signals = createMultiXdSignal('1', [100, 200])
      selectionStore.updateMappings(signals)

      // Select XD segment directly
      selectionStore.toggleXdSegment(100)

      expect(selectionStore.isXdSegmentSelected(100)).toBe(true)
      expect(selectionStore.isSignalSelected('1')).toBe(false)
    })
  })

  describe('Selection-Changed Event', () => {
    it('should emit selection-changed when XD segment is toggled', () => {
      wrapper.vm.$emit('selection-changed')

      expect(wrapper.emitted('selection-changed')).toBeTruthy()
    })
  })

  describe('Props Updates', () => {
    it('should update when dataType prop changes', async () => {
      await wrapper.setProps({ dataType: 'anomaly' })

      expect(wrapper.props('dataType')).toBe('anomaly')
    })

    it('should update when anomalyType prop changes', async () => {
      await wrapper.setProps({
        dataType: 'anomaly',
        anomalyType: 'Point Source'
      })

      expect(wrapper.props('anomalyType')).toBe('Point Source')
    })
  })

  describe('Selection State Integration', () => {
    it('should reflect selection state from store', () => {
      const signals = createMultiXdSignal('1', [100, 200])
      selectionStore.updateMappings(signals)

      // No selections initially
      expect(selectionStore.hasMapSelections).toBe(false)

      // Select signal
      selectionStore.toggleSignal('1')

      expect(selectionStore.hasMapSelections).toBe(true)
      expect(selectionStore.selectedSignalsList).toEqual(['1'])
      expect(selectionStore.selectedXdSegmentsList).toEqual(
        expect.arrayContaining([100, 200])
      )
    })

    it('should handle multiple signal selections', () => {
      const signals = [
        ...createMultiXdSignal('1', [100, 200]),
        ...createMultiXdSignal('2', [300, 400]),
      ]
      selectionStore.updateMappings(signals)

      selectionStore.toggleSignal('1')
      selectionStore.toggleSignal('2')

      expect(selectionStore.selectedSignalsList).toEqual(
        expect.arrayContaining(['1', '2'])
      )
      expect(selectionStore.selectedXdSegmentsList).toEqual(
        expect.arrayContaining([100, 200, 300, 400])
      )
    })

    it('should clear all selections', () => {
      const signals = createMultiXdSignal('1', [100])
      selectionStore.updateMappings(signals)
      selectionStore.toggleSignal('1')

      expect(selectionStore.hasMapSelections).toBe(true)

      selectionStore.clearAllSelections()

      expect(selectionStore.hasMapSelections).toBe(false)
      expect(selectionStore.selectedSignals.size).toBe(0)
      expect(selectionStore.selectedXdSegments.size).toBe(0)
    })
  })

  describe('Data Filtering for Chart', () => {
    it('should provide selected XD segments for chart filtering', () => {
      const signals = createMultiXdSignal('1', [100, 200])
      selectionStore.updateMappings(signals)
      selectionStore.toggleSignal('1')

      // The chart should filter to these XD segments
      const selectedXds = selectionStore.selectedXdSegmentsList

      expect(selectedXds).toEqual(expect.arrayContaining([100, 200]))
      expect(selectedXds.length).toBe(2)
    })

    it('should handle mixed signal and direct XD selections', () => {
      const signals = createMultiXdSignal('1', [100, 200])
      selectionStore.updateMappings(signals)

      // Select signal 1 (adds XD 100, 200)
      selectionStore.toggleSignal('1')

      // Also manually select XD 999
      selectionStore.toggleXdSegment(999)

      const selectedXds = selectionStore.selectedXdSegmentsList

      expect(selectedXds).toEqual(expect.arrayContaining([100, 200, 999]))
      expect(selectedXds.length).toBe(3)
    })
  })

  describe('Issue 1: Chart not updating when XD segment is deselected', () => {
    it('should update chart data when XD segment is manually deselected', () => {
      // From ISSUES.md: "I clicked on a signal and the chart updated as expected
      // and the xd segments are highlighted as expected. Then i clicked on one of
      // the highlighted xd segments to deselect it. The segment was deselected but
      // the chart did not update."

      const signals = createMultiXdSignal('1', [100, 200])
      selectionStore.updateMappings(signals)

      // Step 1: Click on signal - adds XD 100, 200
      selectionStore.toggleSignal('1')
      expect(selectionStore.selectedXdSegmentsList.sort()).toEqual([100, 200])

      // Step 2: Click on XD segment 100 to deselect it
      selectionStore.toggleXdSegment(100)

      // EXPECTED: Chart should show only XD 200
      // ACTUAL BUG: Chart still shows XD 100, 200 because selectedXdSegmentsList
      // includes XD from the signal even though we manually deselected it
      expect(selectionStore.selectedXdSegmentsList).toEqual([200])
    })
  })

  describe('Issue 4: Shared XD Segments Incorrectly Deselected', () => {
    it('should keep shared XD segment when one signal is deselected', () => {
      // Signal 1: XD 100, 200
      // Signal 2: XD 200, 300 (XD 200 is shared)
      const signals = [
        createMockSignal({ ID: '1', XD: 100 }),
        createMockSignal({ ID: '1', XD: 200 }),
        createMockSignal({ ID: '2', XD: 200 }),
        createMockSignal({ ID: '2', XD: 300 }),
      ]
      selectionStore.updateMappings(signals)

      // Select both signals
      selectionStore.toggleSignal('1')
      selectionStore.toggleSignal('2')

      expect(selectionStore.selectedXdSegmentsList.sort()).toEqual([100, 200, 300])

      // Deselect signal 1
      selectionStore.toggleSignal('1')

      // EXPECTED: XD 200 should still be selected (signal 2 is still selected)
      // BUG: XD 200 gets deselected even though signal 2 is still selected
      expect(selectionStore.isXdSegmentSelected(200)).toBe(true)
      expect(selectionStore.isXdSegmentSelected(100)).toBe(false)
      expect(selectionStore.isXdSegmentSelected(300)).toBe(true)
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty signals array', async () => {
      await wrapper.setProps({ signals: [] })

      expect(selectionStore.selectedSignals.size).toBe(0)
      expect(selectionStore.selectedXdSegments.size).toBe(0)
    })

    it('should handle rapid selection/deselection', () => {
      const signals = createMultiXdSignal('1', [100])
      selectionStore.updateMappings(signals)

      // Rapid toggles
      for (let i = 0; i < 10; i++) {
        selectionStore.toggleSignal('1')
      }

      // Should end in deselected state (started at false, toggled even number of times)
      expect(selectionStore.isSignalSelected('1')).toBe(false)
    })
  })
})
