/**
 * Color scale utilities for maps and visualizations
 */

/**
 * Get color for travel time value
 * @param {number} value - Travel time in seconds
 * @returns {string} Color hex code
 */
export function travelTimeColorScale(value) {
  if (value < 30) return '#22c55e' // green
  if (value < 60) return '#eab308' // yellow
  if (value < 120) return '#f97316' // orange
  return '#ef4444' // red
}

/**
 * Get color for anomaly intensity
 * @param {number} count - Anomaly count
 * @param {number} maxCount - Maximum count for normalization
 * @returns {string} Color hex code
 */
export function anomalyColorScale(count, maxCount = 100) {
  const normalized = Math.min(count / maxCount, 1)
  if (normalized < 0.25) return '#22c55e' // green
  if (normalized < 0.5) return '#eab308' // yellow
  if (normalized < 0.75) return '#f97316' // orange
  return '#ef4444' // red
}
