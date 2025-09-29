import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import ApiService from '@/services/api'

export const useGeometryStore = defineStore('geometry', () => {
  const featureCollection = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const hasData = computed(() => {
    const features = featureCollection.value?.features
    return Array.isArray(features) && features.length > 0
  })

  async function loadGeometry(force = false) {
    if (loading.value) return

    if (!force && featureCollection.value) {
      return
    }

    loading.value = true
    error.value = null

    try {
      const data = await ApiService.getXdGeometry()
      featureCollection.value = data
    } catch (err) {
      error.value = err
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    featureCollection,
    loading,
    error,
    hasData,
    loadGeometry
  }
})