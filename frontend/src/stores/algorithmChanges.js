import { defineStore } from 'pinia'
import { ref } from 'vue'
import ApiService from '@/services/api'

// Detected INRIX algorithm changes. There are only a handful, so all events are loaded
// once per session and filtered client-side by each page's date range.
export const useAlgorithmChangesStore = defineStore('algorithmChanges', () => {
  const events = ref([])
  const loaded = ref(false)
  let loadPromise = null

  function load() {
    if (loadPromise) {
      return loadPromise
    }
    loadPromise = (async () => {
      try {
        if (typeof ApiService.getAlgorithmChanges !== 'function') {
          return events.value
        }
        const response = await ApiService.getAlgorithmChanges()
        events.value = Array.isArray(response?.events) ? response.events : []
        loaded.value = true
      } catch (error) {
        console.warn('Algorithm changes unavailable:', error)
        loadPromise = null // allow a retry later
      }
      return events.value
    })()
    return loadPromise
  }

  return { events, loaded, load }
})
