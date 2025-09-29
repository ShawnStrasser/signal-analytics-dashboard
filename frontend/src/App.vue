<template>
  <v-app>
    <v-app-bar color="primary" dark>
      <v-app-bar-title>
        🚦 Signal Analytics Dashboard
      </v-app-bar-title>
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
  </v-app>
</template>

<script setup>
import { onMounted } from 'vue'
import FilterPanel from './components/FilterPanel.vue'
import { useGeometryStore } from '@/stores/geometry'

const routes = [
  {
    path: '/travel-time',
    title: 'Travel Time',
    icon: 'mdi-chart-line',
  },
  {
    path: '/anomalies',
    title: 'Anomalies',
    icon: 'mdi-alert',
  },
]

const geometryStore = useGeometryStore()

onMounted(() => {
  geometryStore.loadGeometry().catch(error => {
    console.error('Failed to load XD geometry on startup:', error)
  })
})
</script>