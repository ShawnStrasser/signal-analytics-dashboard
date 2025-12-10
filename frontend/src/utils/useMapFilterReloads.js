import { watch } from 'vue'

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

  const executeReload = async (type, {
    beforeHook,
    clearSelections
  }) => {
    if (loadingRef?.value) {
      return
    }

    if (shouldAutoZoomRef) {
      shouldAutoZoomRef.value = type === 'geometry'
    }

    loadingRef.value = true
    try {
      if (beforeHook) {
        beforeHook()
      }

      if (type === 'geometry' && clearSelections && selectionStore?.hasMapSelections) {
        selectionStore.clearAllSelections()
      }

      if (type === 'geometry') {
        await reloadOnGeometryChange()
      } else {
        const handler = reloadOnDataChange || reloadOnGeometryChange
        await handler()
      }
    } finally {
      loadingRef.value = false
    }
  }

  watch(geometrySources, async () => {
    await executeReload('geometry', {
      beforeHook: onBeforeGeometryChange,
      clearSelections: clearSelectionsOnGeometryChange
    })
  }, { deep: true })

  if (typeof dataSources === 'function') {
    watch(dataSources, async () => {
      await executeReload('data', {
        beforeHook: onBeforeDataChange,
        clearSelections: false
      })
    }, { deep: true })
  }
}
