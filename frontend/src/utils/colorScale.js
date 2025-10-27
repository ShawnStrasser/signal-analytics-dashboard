/**
 * Color scale utilities for maps and visualizations
 * Uses a colorblind-friendly gradient palette
 */

// Shared color scheme - colorblind-friendly green to yellow to orange to red
const COLOR_SCHEME = {
  green: [76, 175, 80],     // #4caf50 - colorblind-safe green
  yellow: [255, 193, 7],    // #ffc107 - amber/yellow
  orange: [255, 87, 34],    // #ff5722 - orange-red
  red: [211, 47, 47]        // #d32f2f - red
}

// Thresholds for different metrics
const THRESHOLDS = {
  travelTimeIndex: {
    floor: 1.0,     // Below this: flat color
    ceiling: 3.0    // Above this: flat color
  },
  anomaly: {
    floor: 0.0,     // Below this: flat color
    ceiling: 10.0   // Above this: flat color
  }
}

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
 * Generic color scale function using shared color scheme
 * @param {number} value - Input value
 * @param {number} floor - Minimum threshold
 * @param {number} ceiling - Maximum threshold
 * @returns {string} Color hex code
 */
function getColorForValue(value, floor, ceiling) {
  const { green, yellow, orange, red } = COLOR_SCHEME
  const range = ceiling - floor

  // Clamp value to floor and ceiling
  if (value <= floor) {
    return `#${green.map(x => x.toString(16).padStart(2, '0')).join('')}`
  }
  if (value >= ceiling) {
    return `#${red.map(x => x.toString(16).padStart(2, '0')).join('')}`
  }

  // Normalize value to 0-1 range within floor-ceiling
  const normalized = (value - floor) / range

  // Three-segment gradient: green→yellow→orange→red
  if (normalized <= 0.33) {
    // First third: green to yellow
    const factor = normalized / 0.33
    return interpolateColor(green, yellow, factor)
  } else if (normalized <= 0.67) {
    // Middle third: yellow to orange
    const factor = (normalized - 0.33) / 0.34
    return interpolateColor(yellow, orange, factor)
  } else {
    // Final third: orange to red
    const factor = (normalized - 0.67) / 0.33
    return interpolateColor(orange, red, factor)
  }
}

/**
 * Get color for Travel Time Index using gradient
 * Floor: 1.0 (below = flat green), Ceiling: 3.0 (above = flat red)
 * @param {number} tti - Travel Time Index value
 * @returns {string} Color hex code
 */
export function travelTimeColorScale(tti) {
  const { floor, ceiling } = THRESHOLDS.travelTimeIndex
  return getColorForValue(tti, floor, ceiling)
}

/**
 * Get color for anomaly percentage using gradient
 * Floor: 0% (below = flat green), Ceiling: 10% (above = flat red)
 * @param {number} percentage - Anomaly percentage (0-100)
 * @returns {string} Color hex code
 */
export function anomalyColorScale(percentage) {
  const { floor, ceiling } = THRESHOLDS.anomaly
  return getColorForValue(percentage, floor, ceiling)
}

/**
 * Get color for before/after TTI difference
 * Maps difference to diverging color scale:
 * -0.25 or less (improvement) = green
 * 0 (no change) = yellow
 * +0.25 or more (degradation) = red
 * @param {number} difference - TTI After - TTI Before
 * @returns {string} Color hex code
 */
export function beforeAfterDifferenceColorScale(difference) {
  const { green, yellow, red } = COLOR_SCHEME

  // Clamp to range -0.25 to +0.25
  if (difference <= -0.25) {
    return `#${green.map(x => x.toString(16).padStart(2, '0')).join('')}`
  }
  if (difference >= 0.25) {
    return `#${red.map(x => x.toString(16).padStart(2, '0')).join('')}`
  }

  // Normalize difference to 0-1 range
  // -0.25 → 0, 0 → 0.5, +0.25 → 1
  const normalized = (difference + 0.25) / 0.5

  // Two-segment gradient: green→yellow→red
  if (normalized <= 0.5) {
    // First half: green to yellow (-0.25 to 0)
    const factor = normalized / 0.5
    return interpolateColor(green, yellow, factor)
  } else {
    // Second half: yellow to red (0 to +0.25)
    const factor = (normalized - 0.5) / 0.5
    return interpolateColor(yellow, red, factor)
  }
}
