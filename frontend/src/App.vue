<template>
  <v-app>
    <v-app-bar color="primary" dark>
      <v-app-bar-title>
        🚦 Signal Analytics Dashboard
      </v-app-bar-title>

      <!-- Connection status indicator -->
      <template v-slot:append>
        <v-tooltip location="bottom">
          <template v-slot:activator="{ props }">
            <v-chip
              v-bind="props"
              :color="connectionChipColor"
              variant="flat"
              size="small"
            >
              <v-icon :icon="connectionIcon" start></v-icon>
              {{ connectionText }}
            </v-chip>
          </template>
          <span>{{ connectionTooltip }}</span>
        </v-tooltip>
      </template>
    </v-app-bar>

    <v-navigation-drawer permanent>
      <v-list>
        <v-list-item
          v-for="route in routes"
          :key="route.path"
          :to="route.path"
          :prepend-icon="route.icon"
          :title="route.title"
        />
      </v-list>

      <v-divider class="my-4"></v-divider>

      <!-- Filters Section -->
      <FilterPanel />
    </v-navigation-drawer>

    <v-main>
      <v-container fluid>
        <!-- Router view with keep-alive for component persistence -->
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </v-container>
    </v-main>

    <!-- Connection status overlay -->
    <ConnectionStatus
      :status="connectionStatus"
      :error-details="connectionError"
      @retry="checkConnection"
    />
  </v-app>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import FilterPanel from './components/FilterPanel.vue'
import ConnectionStatus from './components/ConnectionStatus.vue'
import { useGeometryStore } from '@/stores/geometry'
import ApiService from '@/services/api'

const routes = [
  {
    path: '/travel-time',
    title: 'Travel Time Index',
    icon: 'mdi-chart-line',
  },
  {
    path: '/anomalies',
    title: 'Anomalies',
    icon: 'mdi-alert',
  },
]

const geometryStore = useGeometryStore()
const connectionStatus = ref('connecting') // 'idle', 'connecting', 'connected', 'error'
const connectionError = ref(null)

const connectionChipColor = computed(() => {
  switch (connectionStatus.value) {
    case 'connected':
      return 'success'
    case 'connecting':
      return 'warning'
    case 'error':
      return 'error'
    default:
      return 'grey'
  }
})

const connectionIcon = computed(() => {
  switch (connectionStatus.value) {
    case 'connected':
      return 'mdi-check-circle'
    case 'connecting':
      return 'mdi-loading mdi-spin'
    case 'error':
      return 'mdi-alert-circle'
    default:
      return 'mdi-help-circle'
  }
})

const connectionText = computed(() => {
  switch (connectionStatus.value) {
    case 'connected':
      return 'Connected'
    case 'connecting':
      return 'Connecting...'
    case 'error':
      return 'Disconnected'
    default:
      return 'Unknown'
  }
})

const connectionTooltip = computed(() => {
  switch (connectionStatus.value) {
    case 'connected':
      return 'Database connection active'
    case 'connecting':
      return 'Establishing database connection...'
    case 'error':
      return connectionError.value || 'Failed to connect to database'
    default:
      return 'Connection status unknown'
  }
})

const checkConnection = async () => {
  connectionStatus.value = 'connecting'
  connectionError.value = null

  try {
    const connected = await ApiService.waitForConnection()
    if (connected) {
      connectionStatus.value = 'connected'
      // Geometry will be loaded by SharedMap when needed (deferred)
      // Don't load it here to avoid duplicate queries
    } else {
      connectionStatus.value = 'error'
      connectionError.value = 'Unable to establish database connection'
    }
  } catch (error) {
    console.error('Connection check failed:', error)
    connectionStatus.value = 'error'
    connectionError.value = error.message
  }
}

onMounted(async () => {
  await checkConnection()
})
</script>