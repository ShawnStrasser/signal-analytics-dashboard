<template>
  <v-alert
    v-if="matchingEvents.length > 0"
    type="warning"
    variant="tonal"
    density="compact"
    class="algorithm-change-notice"
    icon="mdi-alert-outline"
    data-testid="algorithm-change-notice"
  >
    <template v-if="matchingEvents.length === 1">
      <strong>{{ eventLines[0] }}</strong>
      {{ caveat }}
    </template>
    <template v-else>
      <ul class="notice-list">
        <li v-for="(line, index) in eventLines" :key="index"><strong>{{ line }}</strong></li>
      </ul>
      <div>{{ caveat }}</div>
    </template>
  </v-alert>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useAlgorithmChangesStore } from '@/stores/algorithmChanges'
import {
  ALGORITHM_CHANGE_CAVEAT,
  ALGORITHM_CHANGE_CAVEAT_PLURAL,
  describeEvent,
  eventsOverlappingRanges
} from '@/utils/algorithmChanges'

// Shows a warning when the selected date range includes (or spans across) a detected
// INRIX algorithm change. Pass one or more { start, end } ranges ('YYYY-MM-DD').
const props = defineProps({
  ranges: {
    type: Array,
    default: () => []
  }
})

const store = useAlgorithmChangesStore()

onMounted(() => {
  void store.load()
})

const matchingEvents = computed(() => eventsOverlappingRanges(store.events, props.ranges))
const eventLines = computed(() => matchingEvents.value.map(describeEvent))
const caveat = computed(() =>
  matchingEvents.value.length > 1 ? ALGORITHM_CHANGE_CAVEAT_PLURAL : ALGORITHM_CHANGE_CAVEAT
)
</script>

<style scoped>
.algorithm-change-notice {
  /* v-alert defaults to flex: 1 1, which stretches it in the full-height page layouts */
  flex: 0 0 auto;
  font-size: 0.875rem;
  line-height: 1.35;
}

.notice-list {
  margin: 0 0 4px 0;
  padding-left: 18px;
}
</style>
