/**
 * Color scale utilities for maps and visualizations
 * Uses a colorblind-friendly blue-yellow-orange-red gradient palette
 */

/**
 * Interpolate between two colors
 * @param {Array} color1 - RGB array [r, g, b]
 * @param {Array} color2 - RGB array [r, g, b]
 * @param {number} factor - Interpolation factor (0-1)
 * @returns {string} Color hex code
 */
function interpolateColor(color1, color2, factor) {
  const result = color1.slice()
  for (let i = 0; i < 3; i++) {
    result[i] = Math.round(result[i] + factor * (color2[i] - result[i]))
  }
  return `#${result.map(x => x.toString(16).padStart(2, '0')).join('')}`
}

/**
 * Get color for Travel Time Index using gradient
 * Range: 0-1 = green, 1-2 = green→yellow, 2-3 = yellow→orange, 3+ = orange→red
 * @param {number} tti - Travel Time Index value
 * @returns {string} Color hex code
 */
export function travelTimeColorScale(tti) {
  // Color stops: green -> yellow -> orange -> red (more saturated colors)
  const green = [34, 197, 94]    // #22c55e - vibrant green
  const yellow = [234, 179, 8]   // #eab308 - vibrant yellow
  const orange = [249, 115, 22]  // #f97316
  const red = [220, 38, 38]      // #dc2626 - darker red

  if (tti <= 1.0) {
    // Gradient from green at 0 to full green at 1.0
    const factor = Math.min(tti, 1.0)
    const darkGreen = [20, 120, 60]  // darker green for tti near 0
    return interpolateColor(darkGreen, green, factor)
  } else if (tti <= 2.0) {
    // Gradient from green to yellow (1.0 to 2.0)
    const factor = (tti - 1.0) / 1.0
    return interpolateColor(green, yellow, factor)
  } else if (tti <= 3.0) {
    // Gradient from yellow to orange (2.0 to 3.0)
    const factor = (tti - 2.0) / 1.0
    return interpolateColor(yellow, orange, factor)
  } else {
    // Gradient from orange to red (3.0 to 4.0+)
    const factor = Math.min((tti - 3.0) / 1.0, 1.0)
    return interpolateColor(orange, red, factor)
  }
}

/**
 * Get color for anomaly percentage using gradient
 * Range: 0-5% = green, 5-10% = green→yellow, 10-15% = yellow→orange, 15%+ = orange→red
 * @param {number} percentage - Anomaly percentage (0-100)
 * @returns {string} Color hex code
 */
export function anomalyColorScale(percentage) {
  // Color stops: green -> yellow -> orange -> red (same as TTI)
  const green = [34, 197, 94]    // #22c55e - vibrant green
  const yellow = [234, 179, 8]   // #eab308 - vibrant yellow
  const orange = [249, 115, 22]  // #f97316
  const red = [220, 38, 38]      // #dc2626 - darker red

  if (percentage <= 5.0) {
    // Gradient from green at 0% to full green at 5%
    const factor = Math.min(percentage / 5.0, 1.0)
    const darkGreen = [20, 120, 60]  // darker green for percentage near 0
    return interpolateColor(darkGreen, green, factor)
  } else if (percentage <= 10.0) {
    // Gradient from green to yellow (5% to 10%)
    const factor = (percentage - 5.0) / 5.0
    return interpolateColor(green, yellow, factor)
  } else if (percentage <= 15.0) {
    // Gradient from yellow to orange (10% to 15%)
    const factor = (percentage - 10.0) / 5.0
    return interpolateColor(yellow, orange, factor)
  } else {
    // Gradient from orange to red (15% to 20%+)
    const factor = Math.min((percentage - 15.0) / 5.0, 1.0)
    return interpolateColor(orange, red, factor)
  }
}
