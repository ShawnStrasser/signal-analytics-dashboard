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
import { markRaw } from 'vue'
import ApiService from '@/services/api'

let inflightLoad = null

export const useSignalDimensionsStore = defineStore('signalDimensions', {
  state: () => ({
    // Map of signal ID -> dimension data
    dimensions: markRaw(new Map()),
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
    count: (state) => state.dimensions.size,

    /**
     * Get all signals as an array with ID included
     * Useful for "show all signals" toggle on map views
     */
    allSignals: (state) => {
      const signals = []
      state.dimensions.forEach((data, id) => {
        signals.push({
          ID: id,
          ...data
        })
      })
      return signals
    }
  },

  actions: {
    /**
     * Load signal dimension data from backend
     * This should be called once on app initialization
     */
    async loadDimensions() {
      if (this.loaded) {
        return
      }
      // A second page mounting mid-load must wait for the same request instead of
      // returning early and rendering with empty dimensions.
      if (inflightLoad) {
        return inflightLoad
      }
      inflightLoad = this._loadDimensions().finally(() => {
        inflightLoad = null
      })
      return inflightLoad
    },

    async _loadDimensions() {
      this.loading = true
      this.error = null

      try {
        const arrowTable = await ApiService.getDimSignals()
        const data = ApiService.arrowTableToObjects(arrowTable)

        // Build Map for O(1) lookups. markRaw: static lookup data doesn't need
        // per-entry reactive proxies; reassigning the property still notifies getters.
        const next = new Map()
        data.forEach(signal => {
          next.set(String(signal.ID), {
            NAME: signal.NAME,
            LATITUDE: signal.LATITUDE,
            LONGITUDE: signal.LONGITUDE,
            DISTRICT: signal.DISTRICT,
            ODOT_MAINTAINED: signal.ODOT_MAINTAINED
          })
        })
        this.dimensions = markRaw(next)

        this.loaded = true
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
      this.dimensions = markRaw(new Map())
      this.loaded = false
      this.error = null
    }
  }
})
