import { debugLog } from '@/config'
/**
 * XD Dimensions Store
 *
 * Caches dimension data for XD segments (XD, ID, BEARING, ROADNAME, MILES, APPROACH)
 * This data is loaded once on app initialization and doesn't change
 * during the session.
 *
 * Separating dimensions from metrics reduces network traffic by ~80%
 * when filters change, since only TTI metrics need to be re-queried.
 */
import { defineStore } from 'pinia'
import ApiService from '@/services/api'

export const useXdDimensionsStore = defineStore('xdDimensions', {
  state: () => ({
    // Map of XD -> dimension data
    dimensions: new Map(),
    // Loading state
    loading: false,
    loaded: false,
    error: null
  }),

  getters: {
    /**
     * Get dimension data for a specific XD segment
     * @param {number} xd - XD segment ID
     * @returns {Object|null} Dimension data (ID, BEARING, ROADNAME, MILES, APPROACH)
     */
    getXdDimensions: (state) => (xd) => {
      return state.dimensions.get(xd) || null
    },

    /**
     * Check if dimensions are loaded and ready
     */
    isReady: (state) => state.loaded && !state.error,

    /**
     * Get total count of cached XD dimensions
     */
    count: (state) => state.dimensions.size
  },

  actions: {
    /**
     * Load XD dimension data from backend
     * This should be called once on app initialization
     */
    async loadDimensions() {
      if (this.loaded || this.loading) {
        debugLog('🛣️ XD dimensions already loaded/loading')
        return
      }

      const t0 = performance.now()
      debugLog('🛣️ Loading XD dimensions START')
      this.loading = true
      this.error = null

      try {
        const arrowTable = await ApiService.getDimSignalsXd()
        const t1 = performance.now()
        debugLog(`🛣️ XD dimensions fetch took ${(t1 - t0).toFixed(2)}ms`)

        const data = ApiService.arrowTableToObjects(arrowTable)
        const t2 = performance.now()
        debugLog(`🛣️ XD dimensions parse took ${(t2 - t1).toFixed(2)}ms`)

        // Build Map for O(1) lookups
        this.dimensions.clear()
        data.forEach(xd => {
          const xdId = xd.XD
          if (!this.dimensions.has(xdId)) {
            this.dimensions.set(xdId, this.createDimensionEntry(xd))
          } else {
            this.mergeDimensionEntry(this.dimensions.get(xdId), xd)
          }
        })

        this.loaded = true
        const t3 = performance.now()
        debugLog(`🛣️ XD dimensions loaded: ${this.dimensions.size} XD segments in ${(t3 - t0).toFixed(2)}ms`)
      } catch (error) {
        console.error('Failed to load XD dimensions:', error)
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
    },

    createDimensionEntry(xd) {
      const signalId = xd.ID ? String(xd.ID) : null
      return {
        XD: xd.XD,
        ID: signalId,
        BEARING: xd.BEARING,
        COUNTY: xd.COUNTY,
        ROADNAME: xd.ROADNAME,
        MILES: xd.MILES,
        APPROACH: xd.APPROACH,
        EXTENDED: xd.EXTENDED,
        VALID_GEOMETRY: xd.VALID_GEOMETRY,
        signalIds: signalId ? [signalId] : [],
        signalDetails: signalId ? [this.createSignalDetail(xd)] : []
      }
    },

    mergeDimensionEntry(existing, xd) {
      const signalId = xd.ID ? String(xd.ID) : null
      if (signalId && !existing.signalIds.includes(signalId)) {
        existing.signalIds.push(signalId)
        existing.signalDetails.push(this.createSignalDetail(xd))
      }

      const hasApproachRecorded = existing.signalDetails.some(detail => detail.APPROACH)
      if ((xd.APPROACH && !hasApproachRecorded) || (!existing.ID && signalId)) {
        this.assignPrimaryFields(existing, xd)
      }
    },

    assignPrimaryFields(target, source) {
      target.ID = source.ID ? String(source.ID) : target.ID
      target.BEARING = source.BEARING ?? target.BEARING
      target.COUNTY = source.COUNTY ?? target.COUNTY
      target.ROADNAME = source.ROADNAME ?? target.ROADNAME
      target.MILES = source.MILES ?? target.MILES
      target.APPROACH = source.APPROACH ?? target.APPROACH
      target.EXTENDED = source.EXTENDED ?? target.EXTENDED
      target.VALID_GEOMETRY = source.VALID_GEOMETRY ?? target.VALID_GEOMETRY
    },

    createSignalDetail(xd) {
      return {
        ID: xd.ID ? String(xd.ID) : null,
        BEARING: xd.BEARING,
        COUNTY: xd.COUNTY,
        ROADNAME: xd.ROADNAME,
        MILES: xd.MILES,
        APPROACH: xd.APPROACH,
        EXTENDED: xd.EXTENDED,
        VALID_GEOMETRY: xd.VALID_GEOMETRY
      }
    }
  }
})
