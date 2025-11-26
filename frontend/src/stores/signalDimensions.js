import { debugLog } from '@/config'
/**
 * Signal Dimensions Store
 *
 * Caches dimension data for signals (ID, NAME, LATITUDE, LONGITUDE)
 * This data is loaded once on app initialization and doesn't change
 * during the session.
 *
 * Separating dimensions from metrics reduces network traffic by ~80%
 * when filters change, since only TTI metrics need to be re-queried.
 */
import { defineStore } from 'pinia'
import ApiService from '@/services/api'

export const useSignalDimensionsStore = defineStore('signalDimensions', {
  state: () => ({
    // Map of signal ID -> dimension data
    dimensions: new Map(),
    // Loading state
    loading: false,
    loaded: false,
    error: null
  }),

  getters: {
    /**
     * Get dimension data for a specific signal ID
     * @param {string|number} id - Signal ID
     * @returns {Object|null} Dimension data (NAME, LATITUDE, LONGITUDE)
     */
    getSignalDimensions: (state) => (id) => {
      return state.dimensions.get(String(id)) || null
    },

    /**
     * Check if dimensions are loaded and ready
     */
    isReady: (state) => state.loaded && !state.error,

    /**
     * Get total count of cached signal dimensions
     */
    count: (state) => state.dimensions.size
  },

  actions: {
    /**
     * Load signal dimension data from backend
     * This should be called once on app initialization
     */
    async loadDimensions() {
      if (this.loaded || this.loading) {
        debugLog('📊 Signal dimensions already loaded/loading')
        return
      }

      const t0 = performance.now()
      debugLog('📊 Loading signal dimensions START')
      this.loading = true
      this.error = null

      try {
        const arrowTable = await ApiService.getDimSignals()
        const t1 = performance.now()
        debugLog(`📊 Signal dimensions fetch took ${(t1 - t0).toFixed(2)}ms`)

        const data = ApiService.arrowTableToObjects(arrowTable)
        const t2 = performance.now()
        debugLog(`📊 Signal dimensions parse took ${(t2 - t1).toFixed(2)}ms`)

        // Build Map for O(1) lookups
        this.dimensions.clear()
        data.forEach(signal => {
          this.dimensions.set(String(signal.ID), {
            NAME: signal.NAME,
            LATITUDE: signal.LATITUDE,
            LONGITUDE: signal.LONGITUDE,
            DISTRICT: signal.DISTRICT,
            ODOT_MAINTAINED: signal.ODOT_MAINTAINED
          })
        })

        this.loaded = true
        const t3 = performance.now()
        debugLog(`📊 Signal dimensions loaded: ${this.dimensions.size} signals in ${(t3 - t0).toFixed(2)}ms`)
      } catch (error) {
        console.error('Failed to load signal dimensions:', error)
        this.error = error.message
        throw error
      } finally {
        this.loading = false
      }
    },

    /**
     * Clear cached dimensions (for testing/debugging)
     */
    clear() {
      this.dimensions.clear()
      this.loaded = false
      this.error = null
    }
  }
})
