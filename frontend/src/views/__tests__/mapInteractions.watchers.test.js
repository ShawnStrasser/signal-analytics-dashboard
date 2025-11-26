import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { useFiltersStore } from '@/stores/filters'
import { useSelectionStore } from '@/stores/selection'
import { useBeforeAfterFiltersStore } from '@/stores/beforeAfterFilters'
import { useMapFilterReloads } from '@/utils/useMapFilterReloads'

const flush = async () => {
  await nextTick()
  await Promise.resolve()
}

describe('Shared map filter reload behaviour', () => {
  let filtersStore
  let selectionStore
  let consoleSpy

  beforeEach(() => {
    setActivePinia(createPinia())
    filtersStore = useFiltersStore()
    selectionStore = useSelectionStore()
    consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => {
    consoleSpy?.mockRestore()
  })

  describe('TravelTime config', () => {
    it('clears map selections on geometry filters but not on date filters', async () => {
      const shouldAutoZoomMap = ref(false)
      const loading = ref(false)
      const geometryReload = vi.fn().mockResolvedValue()
      const dataReload = vi.fn().mockResolvedValue()

      useMapFilterReloads({
        loggerPrefix: 'TravelTimeTest',
        geometrySources: () => [
          filtersStore.selectedSignalIds,
          filtersStore.maintainedBy,
          filtersStore.approach,
          filtersStore.validGeometry
        ],
        dataSources: () => [
          filtersStore.startDate,
          filtersStore.endDate,
          filtersStore.startHour,
          filtersStore.startMinute,
          filtersStore.endHour,
          filtersStore.endMinute,
          filtersStore.timeFilterEnabled,
          filtersStore.dayOfWeek
        ],
        shouldAutoZoomRef: shouldAutoZoomMap,
        loadingRef: loading,
        selectionStore,
        reloadOnGeometryChange: geometryReload,
        reloadOnDataChange: dataReload
      })

      selectionStore.toggleSignal('1')
      const clearSpy = vi.spyOn(selectionStore, 'clearAllSelections')

      filtersStore.setMaintainedBy('odot')
      await flush()

      expect(clearSpy).toHaveBeenCalledTimes(1)
      expect(geometryReload).toHaveBeenCalledTimes(1)
      expect(dataReload).not.toHaveBeenCalled()
      expect(shouldAutoZoomMap.value).toBe(true)

      selectionStore.toggleSignal('2')
      clearSpy.mockClear()
      filtersStore.setDateRange('2024-01-01', '2024-01-02')
      await flush()

      expect(dataReload).toHaveBeenCalledTimes(1)
      expect(clearSpy).not.toHaveBeenCalled()
      expect(shouldAutoZoomMap.value).toBe(false)
    })
  })

  describe('Anomalies config', () => {
    it('treats anomaly type as geometry change and date range as data change', async () => {
      const shouldAutoZoomMap = ref(false)
      const loading = ref(false)
      const geometryReload = vi.fn().mockResolvedValue()
      const dataReload = vi.fn().mockResolvedValue()

      useMapFilterReloads({
        loggerPrefix: 'AnomaliesTest',
        geometrySources: () => [
          filtersStore.selectedSignalIds,
          filtersStore.maintainedBy,
          filtersStore.approach,
          filtersStore.validGeometry,
          filtersStore.anomalyType
        ],
        dataSources: () => [
          filtersStore.startDate,
          filtersStore.endDate,
          filtersStore.startHour,
          filtersStore.startMinute,
          filtersStore.endHour,
          filtersStore.endMinute,
          filtersStore.timeFilterEnabled,
          filtersStore.dayOfWeek
        ],
        shouldAutoZoomRef: shouldAutoZoomMap,
        loadingRef: loading,
        selectionStore,
        reloadOnGeometryChange: geometryReload,
        reloadOnDataChange: dataReload
      })

      selectionStore.toggleSignal('5')
      const clearSpy = vi.spyOn(selectionStore, 'clearAllSelections')

      filtersStore.setAnomalyType('Point Source')
      await flush()

      expect(clearSpy).toHaveBeenCalledTimes(1)
      expect(geometryReload).toHaveBeenCalledTimes(1)
      expect(shouldAutoZoomMap.value).toBe(true)

      selectionStore.toggleSignal('6')
      clearSpy.mockClear()
      filtersStore.setDateRange('2024-02-01', '2024-02-02')
      await flush()

      expect(clearSpy).not.toHaveBeenCalled()
      expect(dataReload).toHaveBeenCalledTimes(1)
      expect(shouldAutoZoomMap.value).toBe(false)
    })
  })

  describe('BeforeAfter config', () => {
    it('clears selections for geometry filters and reloads data for period changes', async () => {
      const beforeAfterFiltersStore = useBeforeAfterFiltersStore()
      const shouldAutoZoomMap = ref(false)
      const loading = ref(false)
      const geometryReload = vi.fn().mockResolvedValue()
      const dataReload = vi.fn().mockResolvedValue()

      useMapFilterReloads({
        loggerPrefix: 'BeforeAfterTest',
        geometrySources: () => [
          filtersStore.selectedSignalIds,
          filtersStore.maintainedBy,
          filtersStore.approach,
          filtersStore.validGeometry
        ],
        dataSources: () => [
          beforeAfterFiltersStore.beforeStartDate,
          beforeAfterFiltersStore.beforeEndDate,
          beforeAfterFiltersStore.afterStartDate,
          beforeAfterFiltersStore.afterEndDate,
          filtersStore.startHour,
          filtersStore.startMinute,
          filtersStore.endHour,
          filtersStore.endMinute,
          filtersStore.dayOfWeek,
          filtersStore.removeAnomalies
        ],
        shouldAutoZoomRef: shouldAutoZoomMap,
        loadingRef: loading,
        selectionStore,
        reloadOnGeometryChange: geometryReload,
        reloadOnDataChange: dataReload
      })

      selectionStore.toggleSignal('10')
      const clearSpy = vi.spyOn(selectionStore, 'clearAllSelections')

      filtersStore.setMaintainedBy('others')
      await flush()

      expect(clearSpy).toHaveBeenCalledTimes(1)
      expect(geometryReload).toHaveBeenCalledTimes(1)
      expect(shouldAutoZoomMap.value).toBe(true)

      selectionStore.toggleSignal('20')
      clearSpy.mockClear()

      beforeAfterFiltersStore.setBeforeDateRange('2024-03-01', '2024-03-07')
      await flush()

      expect(clearSpy).not.toHaveBeenCalled()
      expect(dataReload).toHaveBeenCalledTimes(1)
      expect(shouldAutoZoomMap.value).toBe(false)
    })
  })

  describe('Changepoints config', () => {
    it('clears selections on geometry tweaks and preserves on date window updates', async () => {
      const shouldAutoZoomMap = ref(false)
      const loading = ref(false)
      const geometryReload = vi.fn().mockResolvedValue()
      const dataReload = vi.fn().mockResolvedValue()

      useMapFilterReloads({
        loggerPrefix: 'ChangepointsTest',
        geometrySources: () => [
          filtersStore.selectedSignalIds,
          filtersStore.maintainedBy,
          filtersStore.approach,
          filtersStore.validGeometry,
          filtersStore.changepointSeverityThreshold
        ],
        dataSources: () => [
          filtersStore.changepointStartDate,
          filtersStore.changepointEndDate
        ],
        shouldAutoZoomRef: shouldAutoZoomMap,
        loadingRef: loading,
        selectionStore,
        reloadOnGeometryChange: geometryReload,
        reloadOnDataChange: dataReload
      })

      selectionStore.toggleSignal('100')
      const clearSpy = vi.spyOn(selectionStore, 'clearAllSelections')

      filtersStore.setMaintainedBy('odot')
      await flush()

      expect(clearSpy).toHaveBeenCalledTimes(1)
      expect(geometryReload).toHaveBeenCalledTimes(1)
      expect(shouldAutoZoomMap.value).toBe(true)

      selectionStore.toggleSignal('200')
      clearSpy.mockClear()
      filtersStore.setChangepointDateRange('2024-04-01', '2024-04-08')
      await flush()

      expect(clearSpy).not.toHaveBeenCalled()
      expect(dataReload).toHaveBeenCalledTimes(1)
      expect(shouldAutoZoomMap.value).toBe(false)
    })
  })
})
