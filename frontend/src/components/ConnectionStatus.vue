<template>
  <v-overlay
    v-model="showOverlay"
    class="align-center justify-center"
    persistent
  >
    <v-card
      class="pa-8"
      min-width="400"
      elevation="12"
    >
      <v-card-text class="text-center">
        <v-progress-circular
          v-if="(status === 'connecting' || status === 'reconnecting') && showConnectingSpinner"
          indeterminate
          size="64"
          color="primary"
          class="mb-4"
        ></v-progress-circular>

        <v-icon
          v-else-if="status === 'error'"
          icon="mdi-alert-circle"
          size="64"
          color="error"
          class="mb-4"
        ></v-icon>

        <div class="text-h5 mb-2">
          {{ statusTitle }}
        </div>

        <div class="text-body-1 text-medium-emphasis">
          {{ statusMessage }}
        </div>

        <div v-if="errorDetails" class="text-caption text-error mt-2">
          {{ errorDetails }}
        </div>

        <v-btn
          v-if="status === 'error'"
          color="primary"
          variant="elevated"
          class="mt-4"
          @click="retry"
        >
          Retry Connection
        </v-btn>
      </v-card-text>
    </v-card>
  </v-overlay>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useDelayedBoolean } from '@/utils/useDelayedBoolean'

const props = defineProps({
  status: {
    type: String,
    default: 'idle' // 'idle', 'connecting', 'reconnecting', 'connected', 'error'
  },
  errorDetails: {
    type: String,
    default: null
  }
})

const emit = defineEmits(['retry'])

const showOverlay = computed(() => {
  return props.status === 'connecting' || props.status === 'error'
})

const statusTitle = computed(() => {
  switch (props.status) {
    case 'connecting':
      return 'Connecting to Database'
    case 'reconnecting':
      return 'Reconnecting to Database'
    case 'error':
      return 'Connection Failed'
    default:
      return ''
  }
})

const showConnectingSpinner = useDelayedBoolean(() => props.status === 'connecting' || props.status === 'reconnecting')

const statusMessage = computed(() => {
  switch (props.status) {
    case 'connecting':
      return 'Connecting to the database. Please wait...'
    case 'reconnecting':
      return 'Database authentication expired. Reconnecting automatically...'
    case 'error':
      return 'Unable to connect to the database. Please check your connection and try again.'
    default:
      return ''
  }
})

const retry = () => {
  emit('retry')
}
</script>
