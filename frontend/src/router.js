import { createRouter, createWebHistory } from 'vue-router'
import TravelTime from './views/TravelTime.vue'
import Anomalies from './views/Anomalies.vue'
import BeforeAfter from './views/BeforeAfter.vue'
import Changepoints from './views/Changepoints.vue'

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
  },
  {
    path: '/before-after',
    name: 'BeforeAfter',
    component: BeforeAfter
  },
  {
    path: '/changepoints',
    name: 'Changepoints',
    component: Changepoints
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
