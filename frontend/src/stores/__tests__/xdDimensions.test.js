/**
 * XD Dimensions Store Tests
 * Ensures dimension caching preserves mappings between signals and XD segments.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import ApiService from '@/services/api'
import { useXdDimensionsStore } from '../xdDimensions'

vi.mock('@/services/api', () => ({
  default: {
    getDimSignalsXd: vi.fn(),
    arrowTableToObjects: vi.fn()
  }
}))

describe('useXdDimensionsStore', () => {
  const sharedXd = 1237038553
  const mockRecords = [
    {
      XD: sharedXd,
      ID: '03097',
      BEARING: 'NB',
      COUNTY: 'Franklin',
      ROADNAME: 'E Broad St',
      MILES: 0.42,
      APPROACH: true,
      EXTENDED: false
    },
    {
      XD: sharedXd,
      ID: '03098',
      BEARING: 'SB',
      COUNTY: 'Franklin',
      ROADNAME: 'E Broad St',
      MILES: 0.42,
      APPROACH: true,
      EXTENDED: false
    }
  ]

  beforeEach(() => {
    setActivePinia(createPinia())
    ApiService.getDimSignalsXd.mockResolvedValue('arrow-table')
    ApiService.arrowTableToObjects.mockReset()
  })

  it('keeps every signal ID for XD segments that belong to multiple signals', async () => {
    const store = useXdDimensionsStore()
    ApiService.arrowTableToObjects.mockReturnValue(mockRecords)

    await store.loadDimensions()

    const xdDimensions = store.getXdDimensions(sharedXd)

    // Expectation: both signal IDs 03097 and 03098 should be preserved for XD 1237038553
    expect(xdDimensions).toBeTruthy()
    expect(xdDimensions.signalIds?.sort()).toEqual(['03097', '03098'])
  })
})
