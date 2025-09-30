import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useMapStateStore = defineStore('mapState', () => {
  // Default center (will be overridden by auto-zoom to data on first load)
  const mapCenter = ref([39.0, -98.0])
  const mapZoom = ref(4)

  function updateMapState(center, zoom) {
    if (center && Array.isArray(center) && center.length === 2) {
      mapCenter.value = center
    }
    if (typeof zoom === 'number' && zoom > 0) {
      mapZoom.value = zoom
    }
  }

  return {
    mapCenter,
    mapZoom,
    updateMapState
  }
})
