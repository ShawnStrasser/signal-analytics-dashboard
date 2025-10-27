/**
 * Global Test Setup
 * Runs before all test files to configure the test environment
 */

import { vi } from 'vitest'

// Mock localStorage for all tests
// This prevents "localStorage.getItem is not a function" errors
// that occur when stores or components try to access localStorage
const localStorageMock = {
  getItem: vi.fn((key) => null),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
}
global.localStorage = localStorageMock

// Mock requestIdleCallback (not available in jsdom)
global.requestIdleCallback = vi.fn((cb) => setTimeout(cb, 0))
