import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useBeforeAfterFiltersStore = defineStore('beforeAfterFilters', () => {
  // Helper to clone dates without mutating originals
  const cloneDate = (date) => new Date(date.getTime())
  const formatDate = (date) => date.toISOString().split('T')[0]

  // Anchor calculations to start of today to avoid timezone drift
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  // After period: previous 7-day window ending yesterday
  const afterEndDateObj = cloneDate(today)
  afterEndDateObj.setDate(afterEndDateObj.getDate() - 1)
  const afterStartDateObj = cloneDate(afterEndDateObj)
  afterStartDateObj.setDate(afterStartDateObj.getDate() - 6)

  // Before period: week immediately prior to the after window
  const beforeEndDateObj = cloneDate(afterStartDateObj)
  beforeEndDateObj.setDate(beforeEndDateObj.getDate() - 1)
  const beforeStartDateObj = cloneDate(beforeEndDateObj)
  beforeStartDateObj.setDate(beforeStartDateObj.getDate() - 6)

  // State - Before period
  const beforeStartDate = ref(formatDate(beforeStartDateObj))
  const beforeEndDate = ref(formatDate(beforeEndDateObj))

  // State - After period
  const afterStartDate = ref(formatDate(afterStartDateObj))
  const afterEndDate = ref(formatDate(afterEndDateObj))

  // Computed - Before filter params
  const beforeFilterParams = computed(() => ({
    start_date: beforeStartDate.value,
    end_date: beforeEndDate.value
  }))

  // Computed - After filter params
  const afterFilterParams = computed(() => ({
    start_date: afterStartDate.value,
    end_date: afterEndDate.value
  }))

  // Actions
  function setBeforeDateRange(start, end) {
    beforeStartDate.value = start
    beforeEndDate.value = end
  }

  function setAfterDateRange(start, end) {
    afterStartDate.value = start
    afterEndDate.value = end
  }

  return {
    // State
    beforeStartDate,
    beforeEndDate,
    afterStartDate,
    afterEndDate,

    // Computed
    beforeFilterParams,
    afterFilterParams,

    // Actions
    setBeforeDateRange,
    setAfterDateRange
  }
})
