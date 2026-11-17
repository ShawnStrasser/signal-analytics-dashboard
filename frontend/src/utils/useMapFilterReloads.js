import { watch, getCurrentInstance, onActivated, onDeactivated } from 'vue'

/**
 * Shared helper that wires geometry/time filter watchers for map-driven pages.
 *
 * @param {Object} options
 * @param {Function} options.geometrySources - Getter returning dependencies that should trigger geometry reloads.
 * @param {Function} [options.dataSources] - Getter returning dependencies for time/data reloads.
 * @param {import('vue').Ref<boolean>} options.shouldAutoZoomRef - Ref that controls SharedMap auto zoom prop.
 * @param {import('vue').Ref<boolean>} options.loadingRef - Ref tracking the page-wide loading state.
 * @param {Object} options.selectionStore - Pinia selection store with hasMapSelections / clearAllSelections.
 * @param {Function} options.reloadOnGeometryChange - Async callback invoked when geometry filters change.
 * @param {Function} [options.reloadOnDataChange] - Async callback invoked when non-geometry filters change.
 * @param {boolean} [options.clearSelectionsOnGeometryChange=true] - Whether to clear map selections.
 * @param {Function} [options.onBeforeGeometryChange] - Optional hook executed before geometry reload begins.
 * @param {Function} [options.onBeforeDataChange] - Optional hook executed before data/time reload begins.
 */
export function useMapFilterReloads({
  geometrySources,
  dataSources,
  shouldAutoZoomRef,
  loadingRef,
  selectionStore,
  reloadOnGeometryChange,
  reloadOnDataChange,
  clearSelectionsOnGeometryChange = true,
  onBeforeGeometryChange,
  onBeforeDataChange
}) {
  if (typeof geometrySources !== 'function') {
    throw new Error('useMapFilterReloads requires a geometrySources getter')
  }
  if (typeof reloadOnGeometryChange !== 'function') {
    throw new Error('useMapFilterReloads requires reloadOnGeometryChange callback')
  }

  // Reload type requested while a reload was running or while the page was hidden.
  // 'geometry' supersedes 'data' because a geometry reload refreshes everything.
  let pendingType = null
  let running = false
  let waitingForLoad = false
  // Pages live inside <keep-alive>; hidden pages must not refetch on every filter
  // change made elsewhere. Outside a component (unit tests) we are always active.
  let isActive = true

  const mergePending = (type) => {
    pendingType = pendingType === 'geometry' || type === 'geometry' ? 'geometry' : 'data'
  }

  const runReload = async (type) => {
    const isGeometry = type === 'geometry'
    const beforeHook = isGeometry ? onBeforeGeometryChange : onBeforeDataChange

    if (shouldAutoZoomRef) {
      shouldAutoZoomRef.value = isGeometry
    }

    loadingRef.value = true
    try {
      if (beforeHook) {
        beforeHook()
      }

      if (isGeometry && clearSelectionsOnGeometryChange && selectionStore?.hasMapSelections) {
        selectionStore.clearAllSelections()
      }

      if (isGeometry) {
        await reloadOnGeometryChange()
      } else {
        const handler = reloadOnDataChange || reloadOnGeometryChange
        await handler()
      }
    } catch (error) {
      console.error('Filter reload failed:', error)
    } finally {
      loadingRef.value = false
    }
  }

  const executeReload = async (type) => {
    if (!isActive) {
      mergePending(type)
      return
    }
    // A reload is in flight (ours or the page's initial load): queue instead of
    // dropping, so the final filter state is always applied once it finishes.
    if (running || loadingRef?.value) {
      mergePending(type)
      if (!running && loadingRef && !waitingForLoad) {
        waitingForLoad = true
        const stop = watch(loadingRef, (value) => {
          if (!value) {
            stop()
            waitingForLoad = false
            flushPending()
          }
        })
      }
      return
    }

    running = true
    try {
      let next = type
      while (next) {
        pendingType = null
        await runReload(next)
        next = isActive ? pendingType : null
      }
    } finally {
      running = false
    }
  }

  const flushPending = () => {
    if (pendingType && !running && isActive) {
      const type = pendingType
      pendingType = null
      executeReload(type)
    }
  }

  if (getCurrentInstance()) {
    onActivated(() => {
      isActive = true
      flushPending()
    })
    onDeactivated(() => {
      isActive = false
    })
  }

  watch(geometrySources, () => executeReload('geometry'), { deep: true })

  if (typeof dataSources === 'function') {
    watch(dataSources, () => executeReload('data'), { deep: true })
  }
}
