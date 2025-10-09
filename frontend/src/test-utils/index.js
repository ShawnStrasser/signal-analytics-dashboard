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
 * Mock signal data factory (DIM_SIGNALS)
 * Creates test signal data with customizable properties
 * Per README.md schema: ID, DISTRICT, LATITUDE, LONGITUDE, ODOT_MAINTAINED, NAME
 */
export function createMockSignal(overrides = {}) {
  return {
    ID: '1',
    NAME: 'Signal 1',
    DISTRICT: 'District 1',
    ODOT_MAINTAINED: true,
    LATITUDE: 39.7392,
    LONGITUDE: -104.9903,
    TRAVEL_TIME_INDEX: 1.2,
    AVG_TRAVEL_TIME: 120,
    RECORD_COUNT: 100,
    ANOMALY_COUNT: 5,
    POINT_SOURCE_COUNT: 2,
    ...overrides
  }
}

/**
 * Mock XD segment data factory (DIM_SIGNALS_XD)
 * Per README.md schema: ID, VALID_GEOMETRY, XD, BEARING, COUNTY, ROADNAME, MILES, APPROACH, EXTENDED
 */
export function createMockXdSegment(overrides = {}) {
  return {
    ID: '1', // Signal ID (VARCHAR)
    XD: 100,
    APPROACH: true,
    VALID_GEOMETRY: true,
    BEARING: '90',
    COUNTY: 'Test County',
    ROADNAME: 'Main St',
    MILES: 0.5,
    EXTENDED: false,
    ...overrides
  }
}

/**
 * Creates multiple XD segments for the same signal ID
 * Simulates a signal with multiple XD segments (approach/extended)
 * Note: Ensures ID is a string per VARCHAR schema
 */
export function createMultiXdSignal(signalId, xdSegments = [100, 200]) {
  return xdSegments.map((xd, index) => createMockXdSegment({
    ID: String(signalId), // Ensure ID is string per VARCHAR schema
    XD: xd,
    APPROACH: index === 0, // First is approach, rest are extended
  }))
}

/**
 * Creates XD segments with overlapping XD values (shared between signals)
 * Useful for testing shared XD segment selection logic
 */
export function createOverlappingSignals() {
  return [
    // Signal 1 has XD 100, 200
    createMockXdSegment({ ID: '1', XD: 100 }),
    createMockXdSegment({ ID: '1', XD: 200 }),
    // Signal 2 has XD 200, 300 (200 is shared with Signal 1)
    createMockXdSegment({ ID: '2', XD: 200 }),
    createMockXdSegment({ ID: '2', XD: 300 }),
    // Signal 3 has XD 400 (no overlap)
    createMockXdSegment({ ID: '3', XD: 400 }),
  ]
}

/**
 * Creates mock signals grouped by district
 * Useful for testing hierarchical district filter
 * ODOT_MAINTAINED is a BOOLEAN per README.md schema
 */
export function createSignalsByDistrict() {
  return [
    // District 1 - ODOT maintained
    createMockSignal({ ID: '101', NAME: 'Signal 101', DISTRICT: 'District 1', ODOT_MAINTAINED: true }),
    createMockSignal({ ID: '102', NAME: 'Signal 102', DISTRICT: 'District 1', ODOT_MAINTAINED: true }),
    createMockSignal({ ID: '103', NAME: 'Signal 103', DISTRICT: 'District 1', ODOT_MAINTAINED: true }),

    // District 2 - Mixed maintenance
    createMockSignal({ ID: '201', NAME: 'Signal 201', DISTRICT: 'District 2', ODOT_MAINTAINED: true }),
    createMockSignal({ ID: '202', NAME: 'Signal 202', DISTRICT: 'District 2', ODOT_MAINTAINED: false }),

    // District 3 - Others maintained (not ODOT)
    createMockSignal({ ID: '301', NAME: 'Signal 301', DISTRICT: 'District 3', ODOT_MAINTAINED: false }),
    createMockSignal({ ID: '302', NAME: 'Signal 302', DISTRICT: 'District 3', ODOT_MAINTAINED: false }),
  ]
}

/**
 * Creates XD segments with duplicate XD values (same XD, different signals)
 * Useful for testing MAX(APPROACH) and MAX(VALID_GEOMETRY) logic
 */
export function createDuplicateXdSegments() {
  return [
    // XD 100 appears twice: once as approach, once as extended
    createMockXdSegment({ ID: '1', XD: 100, APPROACH: true, VALID_GEOMETRY: true, EXTENDED: false }),
    createMockXdSegment({ ID: '2', XD: 100, APPROACH: false, VALID_GEOMETRY: false, EXTENDED: true }),

    // XD 200 appears twice: both as approach
    createMockXdSegment({ ID: '1', XD: 200, APPROACH: true, VALID_GEOMETRY: true, EXTENDED: false }),
    createMockXdSegment({ ID: '3', XD: 200, APPROACH: true, VALID_GEOMETRY: false, EXTENDED: false }),
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
