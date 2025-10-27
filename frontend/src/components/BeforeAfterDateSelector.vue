<template>
  <div class="before-after-date-selector">
    <!-- Before Period -->
    <v-card
      variant="outlined"
      class="period-card mb-3"
      :style="{
        borderColor: `${beforeColor} !important`,
        borderWidth: '2px !important'
      }"
    >
      <v-card-title
        class="py-2 period-header"
        :style="{
          backgroundColor: `${beforeColor}14`,
          color: beforeColor
        }"
      >
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
    <v-card
      variant="outlined"
      class="period-card"
      :style="{
        borderColor: `${afterColor} !important`,
        borderWidth: '2px !important'
      }"
    >
      <v-card-title
        class="py-2 period-header"
        :style="{
          backgroundColor: `${afterColor}14`,
          color: afterColor
        }"
      >
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
import { ref, watch, computed } from 'vue'
import { useBeforeAfterFiltersStore } from '@/stores/beforeAfterFilters'
import { useThemeStore } from '@/stores/theme'

const beforeAfterFiltersStore = useBeforeAfterFiltersStore()
const themeStore = useThemeStore()

// Compute colors based on colorblind mode
const beforeColor = computed(() => {
  // Blue is already colorblind-safe
  return '#1976D2'
})

const afterColor = computed(() => {
  if (themeStore.colorblindMode) {
    return '#E69F00' // Colorblind-safe orange
  } else {
    return '#F57C00'  // Standard orange
  }
})

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

/* Period card styling */
.period-card {
  /* Border colors are applied via inline styles for dynamic colorblind support */
}

.period-header {
  /* Colors are applied via inline styles for dynamic colorblind support */
  font-weight: 600;
  font-size: 0.95rem !important;
}
</style>
