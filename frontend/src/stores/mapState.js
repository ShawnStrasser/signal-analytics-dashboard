import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useMapStateStore = defineStore('mapState', () => {
  // Default center: approximate center of Kansas
  const mapCenter = ref([39.0119, -98.4842])
  const mapZoom = ref(7)

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
