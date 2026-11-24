function startOfDay(date) {
  const copy = new Date(date)
  copy.setHours(0, 0, 0, 0)
  return copy
}

export function getMonitoringDateRange(referenceDate = new Date()) {
  const base = startOfDay(referenceDate)
  const startDate = new Date(base)
  startDate.setDate(startDate.getDate() - 9)
  const endDate = new Date(startDate)
  endDate.setDate(endDate.getDate() + 1)
  return { startDate, endDate }
}

export function formatDateOnly(date) {
  return date.toISOString().split('T')[0]
}

export function getMonitoringDateStrings(referenceDate = new Date()) {
  const { startDate, endDate } = getMonitoringDateRange(referenceDate)
  return {
    start: formatDateOnly(startDate),
    end: formatDateOnly(endDate)
  }
}

// Enduring changepoints are confirmed 21 days after the change; the latest run
// confirms changepoints from 22 days ago (mirrors the report's -22 day window).
export function getEnduringMonitoringDateRange(referenceDate = new Date()) {
  const base = startOfDay(referenceDate)
  const startDate = new Date(base)
  startDate.setDate(startDate.getDate() - 22)
  const endDate = new Date(startDate)
  endDate.setDate(endDate.getDate() + 1)
  return { startDate, endDate }
}

export function getEnduringMonitoringDateStrings(referenceDate = new Date()) {
  const { startDate, endDate } = getEnduringMonitoringDateRange(referenceDate)
  return {
    start: formatDateOnly(startDate),
    end: formatDateOnly(endDate)
  }
}
