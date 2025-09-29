import { createRouter, createWebHistory } from 'vue-router'
import TravelTime from './views/TravelTime.vue'
import Anomalies from './views/Anomalies.vue'

const routes = [
  {
    path: '/',
    redirect: '/travel-time'
  },
  {
    path: '/travel-time',
    name: 'TravelTime',
    component: TravelTime
  },
  {
    path: '/anomalies',
    name: 'Anomalies',
    component: Anomalies
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router