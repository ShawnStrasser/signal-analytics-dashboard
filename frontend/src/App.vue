<template>
  <v-app>
    <v-app-bar color="primary" dark>
      <!-- Hamburger menu button (mobile + desktop when drawer is closed) -->
      <v-app-bar-nav-icon
        @click="toggleDrawer"
      ></v-app-bar-nav-icon>

      <v-app-bar-title class="text-no-wrap">
        <div class="d-inline-flex align-center" style="gap: 10px; white-space: nowrap;">
          <v-img
            src="/analytics-wave.svg"
            alt="Signal Analytics logo"
            width="28"
            height="28"
            cover
          />
          <span>Signal Analytics Dashboard</span>
        </div>
      </v-app-bar-title>

      <!-- Theme and colorblind toggles -->
      <template v-slot:append>
        <!-- Colorblind mode toggle button -->
        <v-tooltip location="bottom">
          <template v-slot:activator="{ props }">
            <v-btn
              v-bind="props"
              :icon="themeStore.colorblindMode ? 'mdi-eye-check' : 'mdi-eye'"
              @click="toggleColorblindMode"
              variant="text"
            ></v-btn>
          </template>
          <span>{{ themeStore.colorblindMode ? 'Disable' : 'Enable' }} colorblind-friendly mode</span>
        </v-tooltip>

        <!-- Theme toggle button -->
        <v-tooltip location="bottom">
          <template v-slot:activator="{ props }">
            <v-btn
              v-bind="props"
              :icon="themeStore.currentTheme === 'dark' ? 'mdi-weather-night' : 'mdi-weather-sunny'"
              @click="toggleTheme"
              variant="text"
            ></v-btn>
          </template>
          <span>Toggle {{ themeStore.currentTheme === 'dark' ? 'light' : 'dark' }} mode</span>
        </v-tooltip>
      </template>
    </v-app-bar>

    <v-navigation-drawer
      v-model="drawer"
      :permanent="isPinned && !mobile"
      :temporary="!isPinned || mobile"
      :width="320"
    >
      <!-- Pin button (desktop only) -->
      <div v-if="!mobile" class="d-flex justify-end pa-2">
        <v-tooltip location="bottom">
          <template v-slot:activator="{ props }">
            <v-btn
              v-bind="props"
              :icon="isPinned ? 'mdi-pin' : 'mdi-pin-outline'"
              @click="togglePin"
              variant="text"
              size="small"
            ></v-btn>
          </template>
          <span>{{ isPinned ? 'Unpin drawer' : 'Pin drawer' }}</span>
        </v-tooltip>
      </div>

      <v-list>
        <v-list-item
          v-for="route in routes"
          :key="route.path"
          :to="route.path"
          :prepend-icon="route.icon"
          :title="route.title"
          @click="onRouteClick"
        />
      </v-list>

      <v-divider class="my-4"></v-divider>

      <!-- Filters Section -->
      <FilterPanel v-if="showFilterPanel" />
    </v-navigation-drawer>

    <v-main>
      <v-container fluid class="pa-4" style="height: 100%;">
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
      v-if="!isCaptchaRoute"
      :status="connectionStatus"
      :error-details="connectionError"
      @retry="checkConnection"
    />
  </v-app>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme, useDisplay } from 'vuetify'
import FilterPanel from './components/FilterPanel.vue'
import ConnectionStatus from './components/ConnectionStatus.vue'
import { useGeometryStore } from '@/stores/geometry'
import { useThemeStore } from '@/stores/theme'
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
  {
    path: '/changepoints',
    title: 'Changepoints',
    icon: 'mdi-chart-bell-curve-cumulative',
  },
  {
    path: '/before-after',
    title: 'Before/After',
    icon: 'mdi-compare',
  },
  {
    path: '/monitoring',
    title: 'Monitoring',
    icon: 'mdi-monitor-dashboard',
  },
]

const route = useRoute()
const geometryStore = useGeometryStore()
const themeStore = useThemeStore()
const vuetifyTheme = useTheme()
const { mobile } = useDisplay()
const connectionStatus = ref('idle') // 'idle', 'connecting', 'connected', 'error'
const connectionError = ref(null)

// Drawer state management
const drawer = ref(true) // Start open by default
const isPinned = ref(true) // Start pinned by default on desktop

// Watch mobile breakpoint to reset drawer behavior
watch(mobile, (isMobile) => {
  if (isMobile) {
    drawer.value = false // Close drawer on mobile by default
  } else if (isPinned.value) {
    drawer.value = true // Open drawer on desktop if pinned
  }
}, { immediate: true })

const toggleDrawer = () => {
  drawer.value = !drawer.value
}

const togglePin = () => {
  isPinned.value = !isPinned.value
  if (isPinned.value) {
    drawer.value = true // Open when pinning
  }
}

const onRouteClick = () => {
  // Close drawer on route click if on mobile or not pinned
  if (mobile.value || !isPinned.value) {
    drawer.value = false
  }
}

// Sync Vuetify theme with theme store
watch(
  () => themeStore.currentTheme,
  (newTheme) => {
    vuetifyTheme.change(newTheme)
  },
  { immediate: true },
)

const toggleTheme = () => {
  themeStore.toggleTheme()
}

const toggleColorblindMode = () => {
  themeStore.toggleColorblindMode()
}

const showFilterPanel = computed(() => route.meta?.showFilters !== false)
const isCaptchaRoute = computed(() => route.name === 'Captcha')

const connectionChipColor = computed(() => {
  switch (connectionStatus.value) {
    case 'idle':
      return 'grey'
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
    case 'idle':
      return 'mdi-help-circle'
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
    case 'idle':
      return 'Idle'
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
    case 'idle':
      return 'Connection check pending'
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
  if (isCaptchaRoute.value) {
    connectionStatus.value = 'idle'
    connectionError.value = null
    return
  }
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
  if (!isCaptchaRoute.value) {
    await checkConnection()
  }
})

watch(isCaptchaRoute, async (onCaptcha) => {
  if (onCaptcha) {
    connectionStatus.value = 'idle'
    connectionError.value = null
    return
  }
  if (connectionStatus.value !== 'connected') {
    await checkConnection()
  }
})
</script>
