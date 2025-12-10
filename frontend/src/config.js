/**
 * Frontend Configuration
 * Silences non-error logging for production builds.
 */

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

export const APP_PRODUCTION_MODE = parseBoolean(env.APP_PRODUCTION_MODE, true)

let consoleSilenced = false

export function applyLoggingPreferences() {
  if (consoleSilenced) {
    return
  }

  if (typeof console !== 'undefined') {
    const noop = () => {}
    console.log = noop
    console.debug = noop
    console.info = noop
    console.warn = noop
    consoleSilenced = true
  }
}

applyLoggingPreferences()
