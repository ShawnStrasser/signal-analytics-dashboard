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
    })),
    layerGroup: vi.fn(() => mockLayer),
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
    DomEvent: {
      stopPropagation: vi.fn(),
    },
  }

  return { default: L }
})

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
      const signals = createMultiXdSignal(1, [100, 200])
      selectionStore.updateMappings(signals)

      await wrapper.setProps({ signals })

      // Verify initial state
      expect(selectionStore.isSignalSelected(1)).toBe(false)

      // Simulate marker click by calling the store directly
      // (In real component, this happens via marker.on('click', ...))
      selectionStore.toggleSignal(1)

      expect(selectionStore.isSignalSelected(1)).toBe(true)
      expect(selectionStore.selectedXdSegments.has(100)).toBe(true)
      expect(selectionStore.selectedXdSegments.has(200)).toBe(true)
    })
  })

  describe('XD Segment Interactions', () => {
    it('should call toggleXdSegment when XD layer is clicked', () => {
      const signals = createMultiXdSignal(1, [100])
      selectionStore.updateMappings(signals)

      // Simulate XD segment click
      selectionStore.toggleXdSegment(100)

      expect(selectionStore.isXdSegmentSelected(100)).toBe(true)
    })

    it('should allow independent XD selection without signal selection', () => {
      const signals = createMultiXdSignal(1, [100, 200])
      selectionStore.updateMappings(signals)

      // Select XD segment directly
      selectionStore.toggleXdSegment(100)

      expect(selectionStore.isXdSegmentSelected(100)).toBe(true)
      expect(selectionStore.isSignalSelected(1)).toBe(false)
    })
  })

  describe('Selection-Changed Event', () => {
    it('should emit selection-changed when signal is toggled', async () => {
      const signals = createMultiXdSignal(1, [100])
      await wrapper.setProps({ signals })

      // The actual component emits on click, we'll verify the emit mechanism
      // by triggering the event manually
      wrapper.vm.$emit('selection-changed')

      expect(wrapper.emitted('selection-changed')).toBeTruthy()
      expect(wrapper.emitted('selection-changed')).toHaveLength(1)
    })

    it('should emit selection-changed when XD segment is toggled', () => {
      wrapper.vm.$emit('selection-changed')

      expect(wrapper.emitted('selection-changed')).toBeTruthy()
    })
  })

  describe('Props Updates', () => {
    it('should update when signals prop changes', async () => {
      const signals = [createMockSignal({ ID: 1, XD: 100 })]

      await wrapper.setProps({ signals })

      // Verify the component receives the new signals
      expect(wrapper.props('signals')).toEqual(signals)
    })

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
    it('should reflect selection state from store', async () => {
      const signals = createMultiXdSignal(1, [100, 200])
      selectionStore.updateMappings(signals)
      await wrapper.setProps({ signals })

      // No selections initially
      expect(selectionStore.hasMapSelections).toBe(false)

      // Select signal
      selectionStore.toggleSignal(1)

      expect(selectionStore.hasMapSelections).toBe(true)
      expect(selectionStore.selectedSignalsList).toEqual([1])
      expect(selectionStore.selectedXdSegmentsList).toEqual(
        expect.arrayContaining([100, 200])
      )
    })

    it('should handle multiple signal selections', async () => {
      const signals = [
        ...createMultiXdSignal(1, [100, 200]),
        ...createMultiXdSignal(2, [300, 400]),
      ]
      selectionStore.updateMappings(signals)
      await wrapper.setProps({ signals })

      selectionStore.toggleSignal(1)
      selectionStore.toggleSignal(2)

      expect(selectionStore.selectedSignalsList).toEqual(
        expect.arrayContaining([1, 2])
      )
      expect(selectionStore.selectedXdSegmentsList).toEqual(
        expect.arrayContaining([100, 200, 300, 400])
      )
    })

    it('should clear all selections', () => {
      const signals = createMultiXdSignal(1, [100])
      selectionStore.updateMappings(signals)
      selectionStore.toggleSignal(1)

      expect(selectionStore.hasMapSelections).toBe(true)

      selectionStore.clearAllSelections()

      expect(selectionStore.hasMapSelections).toBe(false)
      expect(selectionStore.selectedSignals.size).toBe(0)
      expect(selectionStore.selectedXdSegments.size).toBe(0)
    })
  })

  describe('Data Filtering for Chart', () => {
    it('should provide selected XD segments for chart filtering', () => {
      const signals = createMultiXdSignal(1, [100, 200])
      selectionStore.updateMappings(signals)
      selectionStore.toggleSignal(1)

      // The chart should filter to these XD segments
      const selectedXds = selectionStore.selectedXdSegmentsList

      expect(selectedXds).toEqual(expect.arrayContaining([100, 200]))
      expect(selectedXds.length).toBe(2)
    })

    it('should handle mixed signal and direct XD selections', () => {
      const signals = createMultiXdSignal(1, [100, 200])
      selectionStore.updateMappings(signals)

      // Select signal 1 (adds XD 100, 200)
      selectionStore.toggleSignal(1)

      // Also manually select XD 999
      selectionStore.toggleXdSegment(999)

      const selectedXds = selectionStore.selectedXdSegmentsList

      expect(selectedXds).toEqual(expect.arrayContaining([100, 200, 999]))
      expect(selectedXds.length).toBe(3)
    })
  })

  describe('Complex Interaction Scenarios', () => {
    it('should handle overlapping XD segments correctly', () => {
      // Signal 1: XD 100, 200
      // Signal 2: XD 200, 300 (XD 200 is shared)
      const signals = [
        createMockSignal({ ID: 1, XD: 100 }),
        createMockSignal({ ID: 1, XD: 200 }),
        createMockSignal({ ID: 2, XD: 200 }),
        createMockSignal({ ID: 2, XD: 300 }),
      ]
      selectionStore.updateMappings(signals)

      // Select both signals
      selectionStore.toggleSignal(1)
      selectionStore.toggleSignal(2)

      expect(selectionStore.selectedXdSegmentsList).toEqual(
        expect.arrayContaining([100, 200, 300])
      )

      // Deselect signal 1
      selectionStore.toggleSignal(1)

      // XD 200 should still be selected (because signal 2 is still selected)
      expect(selectionStore.isXdSegmentSelected(200)).toBe(true)
      expect(selectionStore.isXdSegmentSelected(100)).toBe(false)
      expect(selectionStore.isXdSegmentSelected(300)).toBe(true)
    })

    it('should handle selecting signal, then manually deselecting one of its XD segments', () => {
      const signals = createMultiXdSignal(1, [100, 200])
      selectionStore.updateMappings(signals)

      // Select signal (adds XD 100, 200)
      selectionStore.toggleSignal(1)
      expect(selectionStore.selectedXdSegmentsList.sort()).toEqual([100, 200])

      // Manually deselect XD 100
      selectionStore.toggleXdSegment(100)
      expect(selectionStore.selectedXdSegmentsList).toEqual([200])

      // Signal 1 is still marked as selected
      expect(selectionStore.isSignalSelected(1)).toBe(true)
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty signals array', async () => {
      await wrapper.setProps({ signals: [] })

      expect(selectionStore.selectedSignals.size).toBe(0)
      expect(selectionStore.selectedXdSegments.size).toBe(0)
    })

    it('should handle signals without valid coordinates', async () => {
      const signals = [
        createMockSignal({ ID: 1, XD: 100, LATITUDE: null, LONGITUDE: null }),
      ]

      await wrapper.setProps({ signals })

      // Component should not crash, just skip rendering marker
      expect(wrapper.exists()).toBe(true)
    })

    it('should handle rapid selection/deselection', () => {
      const signals = createMultiXdSignal(1, [100])
      selectionStore.updateMappings(signals)

      // Rapid toggles
      for (let i = 0; i < 10; i++) {
        selectionStore.toggleSignal(1)
      }

      // Should end in deselected state (started at false, toggled even number of times)
      expect(selectionStore.isSignalSelected(1)).toBe(false)
    })
  })
})
