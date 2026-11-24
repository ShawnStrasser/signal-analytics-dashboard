import { describe, it, expect } from 'vitest'
import {
  approxCount,
  buildAlgorithmChangeMarkLine,
  describeEvent,
  eventForDay,
  eventsOverlappingRange,
  eventsOverlappingRanges,
  formatEventSpan,
  localDateKey,
  toDateKey
} from '@/utils/algorithmChanges'

const SEP_2025 = {
  event_date: '2025-09-30', start_date: '2025-09-30', end_date: '2025-09-30',
  peak_local: '2025-09-30T11:15:00', peak_timestamp: '2025-09-30T11:15:00-07:00', segments: 455, share_slower: 0.635
}
const OCT_2026 = {
  event_date: '2026-10-22', start_date: '2026-10-21', end_date: '2026-10-22',
  peak_local: '2026-10-22T14:30:00', peak_timestamp: '2026-10-22T14:30:00-07:00', segments: 1099, share_slower: 0.915
}
const EVENTS = [SEP_2025, OCT_2026]

describe('algorithm change overlap logic', () => {
  it('matches ranges that include an event day', () => {
    expect(eventsOverlappingRange(EVENTS, '2026-10-22', '2026-10-25')).toEqual([OCT_2026])
    expect(eventsOverlappingRange(EVENTS, '2026-10-15', '2026-10-21')).toEqual([OCT_2026])
  })

  it('matches ranges that span across an event', () => {
    expect(eventsOverlappingRange(EVENTS, '2025-09-01', '2026-11-30')).toEqual([SEP_2025, OCT_2026])
  })

  it('ignores ranges that end before or start after an event', () => {
    expect(eventsOverlappingRange(EVENTS, '2026-10-01', '2026-10-20')).toEqual([])
    expect(eventsOverlappingRange(EVENTS, '2026-10-23', '2026-11-20')).toEqual([])
  })

  it('handles reversed, missing and multiple ranges', () => {
    expect(eventsOverlappingRange(EVENTS, '2026-10-25', '2026-10-20')).toEqual([OCT_2026])
    expect(eventsOverlappingRange(EVENTS, null, null)).toEqual([])
    expect(eventsOverlappingRange([], '2026-01-01', '2026-12-31')).toEqual([])
    expect(eventsOverlappingRanges(EVENTS, [
      { start: '2025-09-30', end: '2025-10-05' },
      { start: '2026-11-01', end: '2026-11-07' }
    ])).toEqual([SEP_2025])
  })

  it('finds the event covering a changepoint day', () => {
    expect(eventForDay(EVENTS, '2026-10-21')).toBe(OCT_2026)
    expect(eventForDay(EVENTS, '2026-10-23')).toBeNull()
    expect(eventForDay(EVENTS, null)).toBeNull()
  })

  it('derives local calendar days from timestamps and keeps plain date keys', () => {
    const local = new Date(2026, 9, 22, 23, 45) // Oct 22, 11:45 PM local
    expect(localDateKey(local)).toBe('2026-10-22')
    expect(localDateKey(local.toISOString())).toBe('2026-10-22')
    expect(localDateKey(local.getTime())).toBe('2026-10-22')
    expect(toDateKey('2026-10-22')).toBe('2026-10-22')
    expect(localDateKey('not a date')).toBeNull()
  })
})

describe('algorithm change text', () => {
  it('formats spans without timezone drift', () => {
    expect(formatEventSpan(OCT_2026)).toBe('Oct 21–22, 2026')
    expect(formatEventSpan(SEP_2025)).toBe('Sep 30, 2025')
    expect(formatEventSpan({ start_date: '2026-10-31', end_date: '2026-11-01' })).toBe('Oct 31–Nov 1, 2026')
    expect(formatEventSpan({ start_date: '2025-12-31', end_date: '2026-01-01' })).toBe('Dec 31, 2025–Jan 1, 2026')
  })

  it('formats segment counts', () => {
    expect(approxCount(1099)).toBe('1,100')
    expect(approxCount(483)).toBe('480')
    expect(approxCount(42)).toBe('42')
  })

  it('describes an event for the notice', () => {
    expect(describeEvent(OCT_2026)).toBe(
      'INRIX algorithm change Oct 21–22, 2026 (~1,100 segments).'
    )
  })
})

describe('algorithm change chart markLine', () => {
  const peak = Date.parse(OCT_2026.peak_timestamp)

  it('marks events whose peak is inside the axis range', () => {
    const markLine = buildAlgorithmChangeMarkLine(EVENTS, { min: peak - 86400000, max: peak + 86400000 })
    expect(markLine.data).toEqual([{ xAxis: peak }])
    expect(markLine.label.formatter).toBe('INRIX algorithm change')
    expect(markLine.silent).toBe(true)
  })

  it('returns undefined when no event is visible', () => {
    expect(buildAlgorithmChangeMarkLine(EVENTS, { min: peak + 1, max: peak + 86400000 })).toBeUndefined()
    expect(buildAlgorithmChangeMarkLine([], { min: 0, max: Infinity })).toBeUndefined()
  })
})
