<template>
  <div class="before-after-date-selector">
    <!-- Before Period -->
    <v-card variant="outlined" class="before-period-card mb-3">
      <v-card-title class="py-2 before-header">
        <v-icon class="mr-2">mdi-calendar-clock</v-icon>
        Before Period
      </v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12">
            <v-text-field
              v-model="localBeforeStartDate"
              label="Start Date"
              type="date"
              density="compact"
              variant="outlined"
              class="before-input"
            />
          </v-col>
          <v-col cols="12">
            <v-text-field
              v-model="localBeforeEndDate"
              label="End Date"
              type="date"
              density="compact"
              variant="outlined"
              class="before-input"
            />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- After Period -->
    <v-card variant="outlined" class="after-period-card">
      <v-card-title class="py-2 after-header">
        <v-icon class="mr-2">mdi-calendar-check</v-icon>
        After Period
      </v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12">
            <v-text-field
              v-model="localAfterStartDate"
              label="Start Date"
              type="date"
              density="compact"
              variant="outlined"
              class="after-input"
            />
          </v-col>
          <v-col cols="12">
            <v-text-field
              v-model="localAfterEndDate"
              label="End Date"
              type="date"
              density="compact"
              variant="outlined"
              class="after-input"
            />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useBeforeAfterFiltersStore } from '@/stores/beforeAfterFilters'

const beforeAfterFiltersStore = useBeforeAfterFiltersStore()

// Local date state with debouncing
const localBeforeStartDate = ref(beforeAfterFiltersStore.beforeStartDate)
const localBeforeEndDate = ref(beforeAfterFiltersStore.beforeEndDate)
const localAfterStartDate = ref(beforeAfterFiltersStore.afterStartDate)
const localAfterEndDate = ref(beforeAfterFiltersStore.afterEndDate)

let dateDebounceTimer = null

// Watch for external changes to store (e.g., programmatic updates)
watch(() => beforeAfterFiltersStore.beforeStartDate, (newVal) => {
  if (newVal !== localBeforeStartDate.value) {
    localBeforeStartDate.value = newVal
  }
})

watch(() => beforeAfterFiltersStore.beforeEndDate, (newVal) => {
  if (newVal !== localBeforeEndDate.value) {
    localBeforeEndDate.value = newVal
  }
})

watch(() => beforeAfterFiltersStore.afterStartDate, (newVal) => {
  if (newVal !== localAfterStartDate.value) {
    localAfterStartDate.value = newVal
  }
})

watch(() => beforeAfterFiltersStore.afterEndDate, (newVal) => {
  if (newVal !== localAfterEndDate.value) {
    localAfterEndDate.value = newVal
  }
})

// Debounced update of store when local values change
watch([localBeforeStartDate, localBeforeEndDate], ([newStart, newEnd]) => {
  clearTimeout(dateDebounceTimer)
  dateDebounceTimer = setTimeout(() => {
    if (newStart !== beforeAfterFiltersStore.beforeStartDate || newEnd !== beforeAfterFiltersStore.beforeEndDate) {
      beforeAfterFiltersStore.setBeforeDateRange(newStart, newEnd)
    }
  }, 500) // 500ms debounce delay
})

watch([localAfterStartDate, localAfterEndDate], ([newStart, newEnd]) => {
  clearTimeout(dateDebounceTimer)
  dateDebounceTimer = setTimeout(() => {
    if (newStart !== beforeAfterFiltersStore.afterStartDate || newEnd !== beforeAfterFiltersStore.afterEndDate) {
      beforeAfterFiltersStore.setAfterDateRange(newStart, newEnd)
    }
  }, 500) // 500ms debounce delay
})
</script>

<style scoped>
.before-after-date-selector {
  padding: 0;
}

/* Before Period Styling (Blue theme) */
.before-period-card {
  border-color: #1976D2 !important;
  border-width: 2px !important;
}

.before-header {
  background-color: rgba(25, 118, 210, 0.08);
  color: #1976D2;
  font-weight: 600;
  font-size: 0.95rem !important;
}

.before-input :deep(.v-field--focused) {
  border-color: #1976D2 !important;
}

.before-input :deep(.v-field) {
  border-color: rgba(25, 118, 210, 0.3);
}

/* After Period Styling (Orange theme) */
.after-period-card {
  border-color: #F57C00 !important;
  border-width: 2px !important;
}

.after-header {
  background-color: rgba(245, 124, 0, 0.08);
  color: #F57C00;
  font-weight: 600;
  font-size: 0.95rem !important;
}

.after-input :deep(.v-field--focused) {
  border-color: #F57C00 !important;
}

.after-input :deep(.v-field) {
  border-color: rgba(245, 124, 0, 0.3);
}
</style>
