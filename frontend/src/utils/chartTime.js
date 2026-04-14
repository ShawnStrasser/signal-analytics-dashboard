const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
export const TIME_OF_DAY_STEP_MINUTES = 15
export const DATE_TIME_STEP_MILLISECONDS = TIME_OF_DAY_STEP_MINUTES * 60 * 1000
const DISPLAY_STEP_MINUTES = [15, 30, 60, 120, 180, 240, 360, 720, 1440]

function padTwoDigits(value) {
  return String(value).padStart(2, '0')
}

function toFiniteNumber(value, fallback = 0) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

function toDate(value) {
  let normalizedValue = value

  if (typeof normalizedValue === 'string') {
    const trimmedValue = normalizedValue.trim()
    if (/^-?\d+(\.\d+)?$/.test(trimmedValue)) {
      normalizedValue = Number(trimmedValue)
    }
  }

  const date = normalizedValue instanceof Date ? new Date(normalizedValue.getTime()) : new Date(normalizedValue)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatClockTime(date) {
  const hours = padTwoDigits(date.getHours())
  const minutes = padTwoDigits(date.getMinutes())
  return `${hours}:${minutes}`
}

function isAlignedToStep(value, step, anchor = 0) {
  if (!Number.isFinite(value) || !Number.isFinite(step) || step <= 0 || !Number.isFinite(anchor)) {
    return false
  }

  const normalizedDifference = ((Math.round(value - anchor) % step) + step) % step
  return normalizedDifference === 0
}

function dataZoomAppliesToAxis(dataZoomConfig, xAxisIndex) {
  if (dataZoomConfig?.xAxisIndex === undefined || dataZoomConfig?.xAxisIndex === null) {
    return true
  }

  if (Array.isArray(dataZoomConfig.xAxisIndex)) {
    return dataZoomConfig.xAxisIndex.includes(xAxisIndex)
  }

  return Number(dataZoomConfig.xAxisIndex) === xAxisIndex
}

export function parseTimeOfDayToMinutes(value) {
  if (value === null || value === undefined || value === '') {
    return 0
  }

  if (typeof value === 'string') {
    const [rawHours = '0', rawMinutes = '0', rawSeconds = '0'] = value.split(':')
    const hours = Number.parseInt(rawHours, 10)
    const minutes = Number.parseInt(rawMinutes, 10)
    const seconds = Number.parseFloat(rawSeconds)

    if (!Number.isFinite(hours) || !Number.isFinite(minutes) || !Number.isFinite(seconds)) {
      return 0
    }

    return hours * 60 + minutes + (seconds / 60)
  }

  if (value instanceof Date) {
    return value.getHours() * 60 + value.getMinutes() + (value.getSeconds() / 60)
  }

  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      return 0
    }

    const absoluteValue = Math.abs(value)

    if (absoluteValue <= 24 * 60) {
      return value
    }

    if (absoluteValue <= 24 * 60 * 60) {
      return value / 60
    }

    if (absoluteValue <= 24 * 60 * 60 * 1000) {
      return value / 1000 / 60
    }

    return value / 1000000 / 60
  }

  return 0
}

export function snapMinutesToTimeBucket(value, mode = 'nearest') {
  const totalMinutes = Math.max(0, toFiniteNumber(value, 0))

  if (mode === 'floor') {
    return Math.floor(totalMinutes / TIME_OF_DAY_STEP_MINUTES) * TIME_OF_DAY_STEP_MINUTES
  }

  if (mode === 'ceil') {
    return Math.ceil(totalMinutes / TIME_OF_DAY_STEP_MINUTES) * TIME_OF_DAY_STEP_MINUTES
  }

  return Math.round(totalMinutes / TIME_OF_DAY_STEP_MINUTES) * TIME_OF_DAY_STEP_MINUTES
}

export function formatTimeOfDayLabel(value) {
  const totalMinutes = snapMinutesToTimeBucket(parseTimeOfDayToMinutes(value), 'nearest')
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60

  return `${padTwoDigits(hours)}:${padTwoDigits(minutes)}`
}

export function getDisplayStepMinutesForRange(rangeMinutes, { maxLabels = 8 } = {}) {
  const normalizedRange = Math.max(TIME_OF_DAY_STEP_MINUTES, Math.ceil(Math.max(0, toFiniteNumber(rangeMinutes, 0)) / TIME_OF_DAY_STEP_MINUTES) * TIME_OF_DAY_STEP_MINUTES)
  const normalizedMaxLabels = Math.max(2, Math.floor(toFiniteNumber(maxLabels, 8)))

  return DISPLAY_STEP_MINUTES.find((step) => normalizedRange / step < normalizedMaxLabels) ?? DISPLAY_STEP_MINUTES[DISPLAY_STEP_MINUTES.length - 1]
}

export function formatTimeOfDayAxisLabel(value, { displayStepMinutes = TIME_OF_DAY_STEP_MINUTES, anchorMinutes = 0 } = {}) {
  const totalMinutes = snapMinutesToTimeBucket(parseTimeOfDayToMinutes(value), 'nearest')
  const anchor = snapMinutesToTimeBucket(anchorMinutes, 'floor')

  if (!isAlignedToStep(totalMinutes, displayStepMinutes, anchor)) {
    return ''
  }

  return formatTimeOfDayLabel(totalMinutes)
}

export function getVisibleAxisRange(chart, { fullMin, fullMax, xAxisIndex = 0 } = {}) {
  if (!Number.isFinite(fullMin) || !Number.isFinite(fullMax) || fullMax <= fullMin) {
    return { min: fullMin, max: fullMax }
  }

  const option = chart?.getOption?.()
  const dataZoomConfigs = option?.dataZoom

  if (!Array.isArray(dataZoomConfigs) || !dataZoomConfigs.length) {
    return { min: fullMin, max: fullMax }
  }

  let visibleMin = fullMin
  let visibleMax = fullMax

  dataZoomConfigs.forEach((dataZoomConfig) => {
    if (!dataZoomAppliesToAxis(dataZoomConfig, xAxisIndex)) {
      return
    }

    const startValue = Number(dataZoomConfig?.startValue)
    const endValue = Number(dataZoomConfig?.endValue)

    if (Number.isFinite(startValue) && Number.isFinite(endValue)) {
      visibleMin = Math.max(visibleMin, startValue)
      visibleMax = Math.min(visibleMax, endValue)
      return
    }

    const startPercent = Number.isFinite(Number(dataZoomConfig?.start)) ? Number(dataZoomConfig.start) : 0
    const endPercent = Number.isFinite(Number(dataZoomConfig?.end)) ? Number(dataZoomConfig.end) : 100
    const range = fullMax - fullMin
    const zoomMin = fullMin + (range * startPercent / 100)
    const zoomMax = fullMin + (range * endPercent / 100)

    visibleMin = Math.max(visibleMin, zoomMin)
    visibleMax = Math.min(visibleMax, zoomMax)
  })

  return {
    min: visibleMin,
    max: visibleMax,
  }
}

export function createTimeOfDayAxisLabelFormatter(chart, { fullMin, fullMax, maxLabels = 8, xAxisIndex = 0 } = {}) {
  return (value) => {
    const { min: visibleMin, max: visibleMax } = getVisibleAxisRange(chart, { fullMin, fullMax, xAxisIndex })
    const displayStepMinutes = getDisplayStepMinutesForRange(visibleMax - visibleMin, { maxLabels })

    return formatTimeOfDayAxisLabel(value, {
      displayStepMinutes,
      anchorMinutes: 0,
    })
  }
}

export function createDateTimeAxisLabelFormatter(chart, { fullMin, fullMax, maxLabels = 8, xAxisIndex = 0, isMobile = false } = {}) {
  return (value) => {
    const { min: visibleMin, max: visibleMax } = getVisibleAxisRange(chart, { fullMin, fullMax, xAxisIndex })
    const displayStepMinutes = getDisplayStepMinutesForRange((visibleMax - visibleMin) / (1000 * 60), { maxLabels })

    return formatDateTimeAxisLabel(value, {
      isMobile,
      displayStepMinutes,
      anchorTimestamp: startOfLocalDayTimestamp(visibleMin),
    })
  }
}

export function snapTimestampToTimeBucket(value, mode = 'nearest') {
  const date = toDate(value)
  if (!date) {
    return 0
  }

  const timestamp = date.getTime()

  if (mode === 'floor') {
    return Math.floor(timestamp / DATE_TIME_STEP_MILLISECONDS) * DATE_TIME_STEP_MILLISECONDS
  }

  if (mode === 'ceil') {
    return Math.ceil(timestamp / DATE_TIME_STEP_MILLISECONDS) * DATE_TIME_STEP_MILLISECONDS
  }

  return Math.round(timestamp / DATE_TIME_STEP_MILLISECONDS) * DATE_TIME_STEP_MILLISECONDS
}

export function startOfLocalDayTimestamp(value) {
  const date = toDate(value)
  if (!date) {
    return 0
  }

  date.setHours(0, 0, 0, 0)
  return date.getTime()
}

export function buildTimeOfDayCategories(values = []) {
  const parsedValues = values
    .map((value) => parseTimeOfDayToMinutes(value))
    .filter((value) => Number.isFinite(value))

  if (!parsedValues.length) {
    return {
      minutes: [],
      labels: [],
      positions: new Map(),
    }
  }

  const minMinutes = snapMinutesToTimeBucket(Math.min(...parsedValues), 'floor')
  const maxMinutes = snapMinutesToTimeBucket(Math.max(...parsedValues), 'ceil')
  const minutes = []

  for (let current = minMinutes; current <= maxMinutes; current += TIME_OF_DAY_STEP_MINUTES) {
    minutes.push(current)
  }

  const labels = minutes.map((minuteValue) => formatTimeOfDayLabel(minuteValue))
  const positions = new Map(minutes.map((minuteValue, index) => [minuteValue, index]))

  return {
    minutes,
    labels,
    positions,
  }
}

export function mapPointsToTimeOfDayCategorySeries(points = [], scale) {
  if (!scale?.minutes?.length) {
    return []
  }

  const values = Array(scale.minutes.length).fill(null)

  points.forEach(([minuteValue, yValue]) => {
    const snappedMinute = snapMinutesToTimeBucket(minuteValue, 'nearest')
    const index = scale.positions.get(snappedMinute)
    if (index !== undefined) {
      values[index] = yValue
    }
  })

  return values
}

export function formatDateTimeAxisLabel(value, { isMobile = false, displayStepMinutes, anchorTimestamp } = {}) {
  const date = toDate(value)
  if (!date) {
    return ''
  }

  if (displayStepMinutes) {
    const timestamp = snapTimestampToTimeBucket(date, 'nearest')
    const anchor = displayStepMinutes >= 1440
      ? startOfLocalDayTimestamp(anchorTimestamp ?? timestamp)
      : snapTimestampToTimeBucket(anchorTimestamp ?? 0, 'floor')

    if (!isAlignedToStep(timestamp, displayStepMinutes * 60 * 1000, anchor)) {
      return ''
    }
  }

  const timeLabel = formatClockTime(date)
  const month = padTwoDigits(date.getMonth() + 1)
  const day = padTwoDigits(date.getDate())
  const dayOfWeek = DAY_NAMES[date.getDay()]

  if (date.getHours() === 0 && date.getMinutes() === 0) {
    if (isMobile) {
      return `${month}/${day}\n${timeLabel}`
    }
    return `${dayOfWeek} ${month}/${day}\n${timeLabel}`
  }

  return timeLabel
}

export function formatDateTimeTooltipLabel(value) {
  const date = toDate(value)
  if (!date) {
    return ''
  }

  const dayOfWeek = DAY_NAMES[date.getDay()]
  const month = padTwoDigits(date.getMonth() + 1)
  const day = padTwoDigits(date.getDate())
  const year = date.getFullYear()
  const timeLabel = formatClockTime(date)

  return `${dayOfWeek} ${month}/${day}/${year} ${timeLabel}`
}