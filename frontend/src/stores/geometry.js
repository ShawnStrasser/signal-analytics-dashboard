import { defineStore } from 'pinia'
import { ref, shallowRef, markRaw, computed } from 'vue'
import ApiService from '@/services/api'

export const useGeometryStore = defineStore('geometry', () => {
  // shallowRef + markRaw: ~16k GeoJSON features must not be deeply proxied
  const featureCollection = shallowRef(null)
  let inflight = null
  const loading = ref(false)
  const error = ref(null)

  const hasData = computed(() => {
    const features = featureCollection.value?.features
    return Array.isArray(features) && features.length > 0
  })

  async function loadGeometry(force = false) {
    if (!force && featureCollection.value) {
      return
    }
    // Concurrent callers share the in-flight request instead of returning early
    if (inflight) {
      return inflight
    }

    loading.value = true
    error.value = null

    inflight = (async () => {
      try {
        const data = await ApiService.getXdGeometry()
        featureCollection.value = data ? markRaw(data) : data
      } catch (err) {
        error.value = err
        throw err
      } finally {
        loading.value = false
        inflight = null
      }
    })()
    return inflight
  }

  return {
    featureCollection,
    loading,
    error,
    hasData,
    loadGeometry
  }
})