/**
 * Frontend Configuration
 * Controls debug logging and performance monitoring
 */

// Enable/disable verbose console logging
// Set to false in production to reduce console noise
export const DEBUG_FRONTEND_LOGGING = true

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
