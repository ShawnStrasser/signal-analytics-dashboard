import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Cache store for map data (travel time and anomaly summaries)
 * Caches "all signals" queries to avoid re-fetching when clearing filters
 */
export const useMapDataCacheStore = defineStore('mapDataCache', () => {
  // Cache for travel time summary data
  const travelTimeCacheAll = ref(null)
  const travelTimeCacheKey = ref(null) // Track date range used for cache

  // Cache for anomaly summary data
  const anomalyCacheAll = ref(null)
  const anomalyCacheKey = ref(null) // Track date range + anomaly type used for cache

  /**
   * Get cached travel time data if available and valid
   * @param {string} startDate - YYYY-MM-DD format
   * @param {string} endDate - YYYY-MM-DD format
   * @returns {Array|null} - Cached data or null
   */
  function getTravelTimeCache(startDate, endDate) {
    const key = `${startDate}|${endDate}`
    if (travelTimeCacheKey.value === key && travelTimeCacheAll.value) {
      console.log('📦 Cache HIT: Travel time summary (all signals)')
      return travelTimeCacheAll.value
    }
    return null
  }

  /**
   * Store travel time data in cache
   * @param {string} startDate - YYYY-MM-DD format
   * @param {string} endDate - YYYY-MM-DD format
   * @param {Array} data - Map summary data
   */
  function setTravelTimeCache(startDate, endDate, data) {
    const key = `${startDate}|${endDate}`
    travelTimeCacheKey.value = key
    travelTimeCacheAll.value = data
    console.log(`📦 Cache SET: Travel time summary (${data.length} records)`)
  }

  /**
   * Get cached anomaly data if available and valid
   * @param {string} startDate - YYYY-MM-DD format
   * @param {string} endDate - YYYY-MM-DD format
   * @param {string} anomalyType - Anomaly type filter
   * @returns {Array|null} - Cached data or null
   */
  function getAnomalyCache(startDate, endDate, anomalyType) {
    const key = `${startDate}|${endDate}|${anomalyType}`
    if (anomalyCacheKey.value === key && anomalyCacheAll.value) {
      console.log('📦 Cache HIT: Anomaly summary (all signals)')
      return anomalyCacheAll.value
    }
    return null
  }

  /**
   * Store anomaly data in cache
   * @param {string} startDate - YYYY-MM-DD format
   * @param {string} endDate - YYYY-MM-DD format
   * @param {string} anomalyType - Anomaly type filter
   * @param {Array} data - Map summary data
   */
  function setAnomalyCache(startDate, endDate, anomalyType, data) {
    const key = `${startDate}|${endDate}|${anomalyType}`
    anomalyCacheKey.value = key
    anomalyCacheAll.value = data
    console.log(`📦 Cache SET: Anomaly summary (${data.length} records)`)
  }

  /**
   * Clear all caches (called when filters change in ways that invalidate cache)
   */
  function clearAllCaches() {
    travelTimeCacheAll.value = null
    travelTimeCacheKey.value = null
    anomalyCacheAll.value = null
    anomalyCacheKey.value = null
    console.log('📦 Cache CLEARED')
  }

  /**
   * Clear only travel time cache
   */
  function clearTravelTimeCache() {
    travelTimeCacheAll.value = null
    travelTimeCacheKey.value = null
    console.log('📦 Cache CLEARED: Travel time')
  }

  /**
   * Clear only anomaly cache
   */
  function clearAnomalyCache() {
    anomalyCacheAll.value = null
    anomalyCacheKey.value = null
    console.log('📦 Cache CLEARED: Anomaly')
  }

  return {
    // Travel time cache
    getTravelTimeCache,
    setTravelTimeCache,
    clearTravelTimeCache,

    // Anomaly cache
    getAnomalyCache,
    setAnomalyCache,
    clearAnomalyCache,

    // Global
    clearAllCaches
  }
})
