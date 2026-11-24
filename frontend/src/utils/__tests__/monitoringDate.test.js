import { describe, it, expect } from 'vitest'
import {
  formatDateRangeLabel,
  getEnduringMonitoringDateStrings,
  getMonitoringDateStrings,
  getMonitoringReportDateString
} from '@/utils/monitoringDate'

describe('monitoring report windows (match the emailed report)', () => {
  const reportDate = new Date(2026, 9, 31, 7, 30) // Oct 31, 2026 local

  it('uses single days: new changepoints R-9, enduring R-22', () => {
    expect(getMonitoringReportDateString(reportDate)).toBe('2026-10-31')
    expect(getMonitoringDateStrings(reportDate)).toEqual({ start: '2026-10-22', end: '2026-10-22' })
    expect(getEnduringMonitoringDateStrings(reportDate)).toEqual({ start: '2026-10-09', end: '2026-10-09' })
  })

  it('uses the local calendar date late in the evening', () => {
    expect(getMonitoringReportDateString(new Date(2026, 10, 24, 23, 55))).toBe('2026-11-24')
  })

  it('labels single-day windows with one date', () => {
    expect(formatDateRangeLabel({ start: '2026-10-22', end: '2026-10-22' })).toBe('2026-10-22')
    expect(formatDateRangeLabel({ start: '2026-10-22', end: '2026-10-23' })).toBe('2026-10-22 to 2026-10-23')
  })
})
