import { ref, watch, onBeforeUnmount } from 'vue'

/**
 * Returns a ref that only becomes true if the watched source
 * stays truthy for the provided delay. Helpful for hiding spinners
 * during fast-loading states.
 *
 * @param {import('vue').WatchSource<boolean>} source
 * @param {number} delayMs
 * @returns {import('vue').Ref<boolean>}
 */
export function useDelayedBoolean(source, delayMs = 1500) {
  const delayed = ref(false)
  let timerId = null

  const clearTimer = () => {
    if (timerId !== null) {
      clearTimeout(timerId)
      timerId = null
    }
  }

  watch(source, (value) => {
    if (value) {
      if (delayed.value || timerId !== null) {
        return
      }
      timerId = setTimeout(() => {
        delayed.value = true
        timerId = null
      }, delayMs)
    } else {
      delayed.value = false
      clearTimer()
    }
  }, { immediate: true })

  onBeforeUnmount(() => {
    clearTimer()
  })

  return delayed
}
