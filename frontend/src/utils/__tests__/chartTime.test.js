import { describe, expect, it } from 'vitest'

import {
  buildTimeOfDayCategories,
  createDateTimeAxisLabelFormatter,
  createTimeOfDayAxisLabelFormatter,
  DATE_TIME_STEP_MILLISECONDS,
  formatDateTimeAxisLabel,
  formatDateTimeTooltipLabel,
  formatTimeOfDayAxisLabel,
  formatTimeOfDayLabel,
  getVisibleAxisRange,
  getDisplayStepMinutesForRange,
  mapPointsToTimeOfDayCategorySeries,
  parseTimeOfDayToMinutes,
  snapTimestampToTimeBucket,
} from '../chartTime'

describe('chartTime utilities', () => {
  it('parses time-of-day strings, dates, and Arrow-style numeric values', () => {
    expect(parseTimeOfDayToMinutes('19:00:00')).toBe(1140)

    const dateValue = new Date(2026, 3, 14, 19, 15, 30)
    expect(parseTimeOfDayToMinutes(dateValue)).toBeCloseTo(1155.5)

    const arrowMicroseconds = ((19 * 3600) + (15 * 60) + 30) * 1000000
    expect(parseTimeOfDayToMinutes(arrowMicroseconds)).toBeCloseTo(1155.5)
  })

  it('formats time-of-day labels in 15-minute buckets without decimals', () => {
    expect(formatTimeOfDayLabel(485.699999999)).toBe('08:00')
    expect(formatTimeOfDayLabel(1140)).toBe('19:00')
  })

  it('formats date-time axis labels consistently', () => {
    const midnightValue = new Date(2026, 3, 14, 0, 0, 0).getTime()
    const daytimeValue = new Date(2026, 3, 14, 19, 0, 0).getTime()

    expect(formatDateTimeAxisLabel(midnightValue, { isMobile: false })).toBe('Tue 04/14\n00:00')
    expect(formatDateTimeAxisLabel(daytimeValue, { isMobile: false })).toBe('19:00')
  })

  it('formats tooltip timestamps without seconds', () => {
    const timestamp = new Date(2026, 3, 14, 19, 0, 0).getTime()
    expect(formatDateTimeTooltipLabel(timestamp)).toBe('Tue 04/14/2026 19:00')
  })

  it('builds quarter-hour categories and maps points onto them', () => {
    const scale = buildTimeOfDayCategories([480, 495, 540])

    expect(scale.labels).toEqual(['08:00', '08:15', '08:30', '08:45', '09:00'])
    expect(mapPointsToTimeOfDayCategorySeries([[480, 1.1], [540, 1.3]], scale)).toEqual([1.1, null, null, null, 1.3])
  })

  it('snaps date-time values to quarter-hour buckets', () => {
    const timestamp = new Date(2026, 3, 14, 11, 37, 0).getTime()

    expect(snapTimestampToTimeBucket(timestamp, 'floor')).toBe(new Date(2026, 3, 14, 11, 30, 0).getTime())
    expect(snapTimestampToTimeBucket(timestamp, 'ceil')).toBe(new Date(2026, 3, 14, 11, 45, 0).getTime())
    expect(DATE_TIME_STEP_MILLISECONDS).toBe(900000)
  })

  it('chooses coarser label steps for large ranges', () => {
    expect(getDisplayStepMinutesForRange(180, { maxLabels: 8 })).toBe(30)
    expect(getDisplayStepMinutesForRange(1440, { maxLabels: 8 })).toBe(240)
  })

  it('hides axis labels that do not align to the display step', () => {
    expect(formatTimeOfDayAxisLabel(495, { displayStepMinutes: 60, anchorMinutes: 480 })).toBe('')
    expect(formatTimeOfDayAxisLabel(540, { displayStepMinutes: 60, anchorMinutes: 480 })).toBe('09:00')
    expect(formatDateTimeAxisLabel(new Date(2026, 3, 14, 10, 15, 0).getTime(), { displayStepMinutes: 60, anchorTimestamp: new Date(2026, 3, 14, 10, 0, 0).getTime() })).toBe('')
  })

  it('derives the visible range from dataZoom configuration', () => {
    const chart = {
      getOption: () => ({
        dataZoom: [{ start: 25, end: 50, xAxisIndex: 0 }]
      })
    }

    expect(getVisibleAxisRange(chart, { fullMin: 0, fullMax: 120, xAxisIndex: 0 })).toEqual({ min: 30, max: 60 })
  })

  it('updates label formatters from the live zoom window', () => {
    const chart = {
      getOption: () => ({
        dataZoom: [{ start: 0, end: 100, xAxisIndex: 0 }]
      })
    }

    const timeFormatter = createTimeOfDayAxisLabelFormatter(chart, { fullMin: 360, fullMax: 1080, maxLabels: 6 })
    expect(timeFormatter(375)).toBe('')

    chart.getOption = () => ({
      dataZoom: [{ start: 25, end: 35, xAxisIndex: 0 }]
    })
    expect(timeFormatter(375)).toBe('06:15')

    const timestampFormatter = createDateTimeAxisLabelFormatter(chart, {
      fullMin: new Date(2026, 3, 14, 6, 0, 0).getTime(),
      fullMax: new Date(2026, 3, 14, 18, 0, 0).getTime(),
      maxLabels: 6,
      isMobile: false,
    })

    chart.getOption = () => ({
      dataZoom: [{ start: 0, end: 100, xAxisIndex: 0 }]
    })
    expect(timestampFormatter(new Date(2026, 3, 14, 6, 15, 0).getTime())).toBe('')

    chart.getOption = () => ({
      dataZoom: [{ start: 20, end: 30, xAxisIndex: 0 }]
    })
    expect(timestampFormatter(new Date(2026, 3, 14, 8, 15, 0).getTime())).toBe('08:15')
  })
})