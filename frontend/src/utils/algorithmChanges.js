// Helpers for detected INRIX algorithm changes (system-wide travel time shifts).
// Event dates are 'YYYY-MM-DD' strings and are compared as strings (never via
// new Date('YYYY-MM-DD'), which parses as UTC and lands on the previous day in Oregon).

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DATE_KEY_PATTERN = /^\d{4}-\d{2}-\d{2}$/

function pad2(value) {
  return String(value).padStart(2, '0')
}

function parseDateKey(key) {
  if (typeof key !== 'string' || !DATE_KEY_PATTERN.test(key.slice(0, 10))) {
    return null
  }
  const [year, month, day] = key.slice(0, 10).split('-').map(Number)
  return { year, month, day }
}

// Normalize a filter date (string, Date) to a 'YYYY-MM-DD' key.
export function toDateKey(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }
  if (typeof value === 'string' && DATE_KEY_PATTERN.test(value.slice(0, 10)) && value.length <= 10) {
    return value.slice(0, 10)
  }
  return localDateKey(value)
}

// Local calendar day of a timestamp (Arrow timestamps arrive as UTC ISO strings or epoch ms).
export function localDateKey(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) {
    return null
  }
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`
}

// Events whose [start_date, end_date] span overlaps any of the inclusive ranges.
// A range that spans across an event (starts before, ends after) also overlaps.
export function eventsOverlappingRanges(events, ranges) {
  if (!Array.isArray(events) || events.length === 0) {
    return []
  }
  const normalized = (Array.isArray(ranges) ? ranges : [ranges])
    .map(range => {
      let start = toDateKey(range?.start)
      let end = toDateKey(range?.end)
      if (!start && !end) return null
      if (start && end && start > end) {
        [start, end] = [end, start]
      }
      return { start, end }
    })
    .filter(Boolean)
  if (normalized.length === 0) {
    return []
  }
  return events.filter(event => normalized.some(({ start, end }) =>
    (!start || event.end_date >= start) && (!end || event.start_date <= end)
  ))
}

export function eventsOverlappingRange(events, start, end) {
  return eventsOverlappingRanges(events, [{ start, end }])
}

export function eventForDay(events, dayKey) {
  if (!dayKey || !Array.isArray(events)) {
    return null
  }
  return events.find(event => event.start_date <= dayKey && dayKey <= event.end_date) || null
}

function monthDay(parts) {
  return `${MONTHS[parts.month - 1]} ${parts.day}`
}

// 'Sep 30, 2025', 'Oct 21–22, 2026', 'Oct 31–Nov 1, 2026', 'Dec 31, 2025–Jan 1, 2026'
export function formatEventSpan(event) {
  const start = parseDateKey(event?.start_date)
  const end = parseDateKey(event?.end_date)
  if (!start || !end) {
    return ''
  }
  if (event.start_date === event.end_date) {
    return `${monthDay(end)}, ${end.year}`
  }
  if (start.year !== end.year) {
    return `${monthDay(start)}, ${start.year}–${monthDay(end)}, ${end.year}`
  }
  if (start.month === end.month) {
    return `${monthDay(start)}–${end.day}, ${end.year}`
  }
  return `${monthDay(start)}–${monthDay(end)}, ${end.year}`
}

// 1099 -> '1,100', 483 -> '480'
export function approxCount(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) {
    return ''
  }
  let rounded = Math.round(numeric)
  if (numeric >= 1000) {
    rounded = Math.round(numeric / 100) * 100
  } else if (numeric >= 100) {
    rounded = Math.round(numeric / 10) * 10
  }
  return rounded.toLocaleString('en-US')
}

// 'INRIX algorithm change Oct 21–22, 2026 (~1,100 segments).'
export function describeEvent(event) {
  const count = approxCount(event?.segments)
  const suffix = count ? ` (~${count} segments)` : ''
  return `INRIX algorithm change ${formatEventSpan(event)}${suffix}.`
}

export const ALGORITHM_CHANGE_CAVEAT = 'Data across it may not be comparable.'

export const ALGORITHM_CHANGE_CAVEAT_PLURAL = 'Data across them may not be comparable.'

export function peakTimestampMs(event) {
  const parsed = Date.parse(event?.peak_timestamp ?? '')
  return Number.isFinite(parsed) ? parsed : null
}

// ECharts markLine for date/time charts; only events whose peak falls inside [min, max].
export function buildAlgorithmChangeMarkLine(events, { min, max, color = '#E65100', textColor } = {}) {
  if (!Array.isArray(events) || events.length === 0) {
    return undefined
  }
  const data = events
    .map(event => peakTimestampMs(event))
    .filter(ms => ms !== null && (!Number.isFinite(min) || ms >= min) && (!Number.isFinite(max) || ms <= max))
    .map(ms => ({ xAxis: ms }))
  if (data.length === 0) {
    return undefined
  }
  return {
    silent: true,
    symbol: ['none', 'none'],
    animation: false,
    lineStyle: { color, type: 'dashed', width: 1.5 },
    label: {
      show: true,
      formatter: 'INRIX algorithm change',
      position: 'insideEndTop',
      color: textColor ?? color,
      fontSize: 11
    },
    data
  }
}
