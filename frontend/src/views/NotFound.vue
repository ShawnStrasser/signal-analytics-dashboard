<template>
  <v-container class="fill-height d-flex align-center justify-center text-center">
    <v-card class="pa-8" elevation="2" max-width="480">
      <v-icon size="64" color="primary" class="mb-4">mdi-compass-off</v-icon>
      <div class="text-h4 mb-2">Page not found</div>
      <div class="text-body-1 mb-6">
        The page you requested does not exist or may have moved.
      </div>
      <v-btn color="primary" @click="goHome" prepend-icon="mdi-home">
        Back to Travel Time
      </v-btn>
    </v-card>
  </v-container>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push('/travel-time')
}
</script>
