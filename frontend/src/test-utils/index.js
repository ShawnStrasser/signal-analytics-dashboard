/**
 * Test Utilities
 * Helper functions for setting up tests with Pinia stores and mock data
 */

import { createPinia, setActivePinia } from 'pinia'

/**
 * Creates a fresh Pinia instance for testing
 * Call this in beforeEach() to ensure test isolation
 */
export function setupTestPinia() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return pinia
}

/**
 * Mock signal data factory
 * Creates test signal data with customizable properties
 */
export function createMockSignal(overrides = {}) {
  return {
    ID: 1,
    XD: 100,
    LATITUDE: 39.7392,
    LONGITUDE: -104.9903,
    APPROACH: true,
    VALID_GEOMETRY: true,
    TRAVEL_TIME_INDEX: 1.2,
    AVG_TRAVEL_TIME: 120,
    RECORD_COUNT: 100,
    ANOMALY_COUNT: 5,
    POINT_SOURCE_COUNT: 2,
    ...overrides
  }
}

/**
 * Creates multiple mock signals with the same signal ID but different XD segments
 * Simulates a signal with multiple XD segments (approach/extended)
 */
export function createMultiXdSignal(signalId, xdSegments = [100, 200]) {
  return xdSegments.map((xd, index) => createMockSignal({
    ID: signalId,
    XD: xd,
    APPROACH: index === 0, // First is approach, rest are extended
  }))
}

/**
 * Creates mock signals with overlapping XD segments
 * Useful for testing shared XD segment selection logic
 */
export function createOverlappingSignals() {
  return [
    // Signal 1 has XD 100, 200
    createMockSignal({ ID: 1, XD: 100 }),
    createMockSignal({ ID: 1, XD: 200 }),
    // Signal 2 has XD 200, 300 (200 is shared with Signal 1)
    createMockSignal({ ID: 2, XD: 200 }),
    createMockSignal({ ID: 2, XD: 300 }),
    // Signal 3 has XD 400 (no overlap)
    createMockSignal({ ID: 3, XD: 400 }),
  ]
}

/**
 * Mock Leaflet objects for component testing
 */
export function createMockLeafletMap() {
  return {
    setView: vi.fn().mockReturnThis(),
    getCenter: vi.fn().mockReturnValue({ lat: 39.7392, lng: -104.9903 }),
    getZoom: vi.fn().mockReturnValue(13),
    fitBounds: vi.fn(),
    remove: vi.fn(),
    on: vi.fn(),
    addLayer: vi.fn(),
    removeLayer: vi.fn(),
    removeControl: vi.fn(),
  }
}

export function createMockLeafletMarker() {
  return {
    setIcon: vi.fn(),
    bindTooltip: vi.fn().mockReturnThis(),
    setTooltipContent: vi.fn(),
    getTooltip: vi.fn().mockReturnValue({}),
    on: vi.fn(),
    getLatLng: vi.fn().mockReturnValue({ lat: 39.7392, lng: -104.9903 }),
  }
}

export function createMockLeafletLayer() {
  return {
    addTo: vi.fn().mockReturnThis(),
    eachLayer: vi.fn(),
    clearLayers: vi.fn(),
    setStyle: vi.fn(),
    getBounds: vi.fn().mockReturnValue({
      isValid: () => true,
      getNorth: () => 40.0,
      getSouth: () => 39.5,
      getEast: () => -104.5,
      getWest: () => -105.0,
    }),
  }
}
