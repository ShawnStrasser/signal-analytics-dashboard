/**
 * Frontend Configuration
 * Controls debug logging and performance monitoring
 */

// Enable/disable verbose console logging
// Mirrors backend APP_PRODUCTION_MODE flag so prod builds stay quiet
const env = import.meta.env || {}

function parseBoolean(value, fallback = false) {
  if (value === undefined || value === null) {
    return fallback
  }
  if (typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'string') {
    return value.toLowerCase() === 'true'
  }
  return fallback
}

export const APP_PRODUCTION_MODE = parseBoolean(env.APP_PRODUCTION_MODE, false)
export const DEBUG_FRONTEND_LOGGING = !APP_PRODUCTION_MODE

let consoleSilenced = false

export function applyLoggingPreferences() {
  if (consoleSilenced || DEBUG_FRONTEND_LOGGING) {
    return
  }

  if (typeof console !== 'undefined') {
    const noop = () => {}
    console.log = noop
    console.debug = noop
    console.info = noop
    consoleSilenced = true
  }
}

applyLoggingPreferences()

// Helper function to conditionally log
export function debugLog(...args) {
  if (DEBUG_FRONTEND_LOGGING) {
    console.log(...args)
  }
}

// Helper function for timing logs
export function debugTime(label, fn) {
  if (!DEBUG_FRONTEND_LOGGING) {
    return fn()
  }

  const start = performance.now()
  const result = fn()
  const end = performance.now()
  console.log(`⏱️ ${label}: ${(end - start).toFixed(2)}ms`)
  return result
}

// Helper function for async timing logs
export async function debugTimeAsync(label, fn) {
  if (!DEBUG_FRONTEND_LOGGING) {
    return await fn()
  }

  const start = performance.now()
  const result = await fn()
  const end = performance.now()
  console.log(`⏱️ ${label}: ${(end - start).toFixed(2)}ms`)
  return result
}
