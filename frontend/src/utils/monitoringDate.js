// Monitoring report windows for report date R (mirrors services/report_service.py):
// anomalies from R-1, new changepoints from R-9, enduring changepoints from R-22.
// Each changepoint window is a single day (start === end; the API end date is inclusive).
export const NEW_CHANGEPOINT_LAG_DAYS = 9
export const ENDURING_CHANGEPOINT_LAG_DAYS = 22

function startOfDay(date) {
  const copy = new Date(date)
  copy.setHours(0, 0, 0, 0)
  return copy
}

function singleDayRange(referenceDate, lagDays) {
  const startDate = startOfDay(referenceDate)
  startDate.setDate(startDate.getDate() - lagDays)
  return { startDate, endDate: new Date(startDate) }
}

// Local calendar date (not UTC) as YYYY-MM-DD
export function formatDateOnly(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function getMonitoringReportDateString(referenceDate = new Date()) {
  return formatDateOnly(startOfDay(referenceDate))
}

export function getMonitoringDateRange(referenceDate = new Date()) {
  return singleDayRange(referenceDate, NEW_CHANGEPOINT_LAG_DAYS)
}

export function getMonitoringDateStrings(referenceDate = new Date()) {
  const { startDate, endDate } = getMonitoringDateRange(referenceDate)
  return {
    start: formatDateOnly(startDate),
    end: formatDateOnly(endDate)
  }
}

// Enduring changepoints are confirmed 21 days after the change; the latest run
// confirms changepoints from 22 days ago (mirrors the report's R-22 window).
export function getEnduringMonitoringDateRange(referenceDate = new Date()) {
  return singleDayRange(referenceDate, ENDURING_CHANGEPOINT_LAG_DAYS)
}

export function getEnduringMonitoringDateStrings(referenceDate = new Date()) {
  const { startDate, endDate } = getEnduringMonitoringDateRange(referenceDate)
  return {
    start: formatDateOnly(startDate),
    end: formatDateOnly(endDate)
  }
}

export function formatDateRangeLabel({ start, end }) {
  return start === end ? start : `${start} to ${end}`
}
