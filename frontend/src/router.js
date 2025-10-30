import { createRouter, createWebHistory } from 'vue-router'
import TravelTime from './views/TravelTime.vue'
import Anomalies from './views/Anomalies.vue'
import BeforeAfter from './views/BeforeAfter.vue'
import Changepoints from './views/Changepoints.vue'
import Monitoring from './views/Monitoring.vue'
import Captcha from './views/Captcha.vue'
import { isCaptchaVerified } from './utils/captchaSession'

const routes = [
  {
    path: '/',
    redirect: '/travel-time'
  },
  {
    path: '/captcha',
    name: 'Captcha',
    component: Captcha,
    meta: { skipCaptcha: true, showFilters: false }
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
  },
  {
    path: '/monitoring',
    name: 'Monitoring',
    component: Monitoring
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  if (to.meta?.skipCaptcha) {
    next()
    return
  }

  if (typeof window === 'undefined' || isCaptchaVerified()) {
    next()
    return
  }

  const fallbackPath = '/travel-time'
  let redirectTarget = to.fullPath || fallbackPath

  if (redirectTarget === '/' || redirectTarget === '/captcha') {
    redirectTarget = fallbackPath
  }

  next({
    name: 'Captcha',
    query: { redirect: redirectTarget }
  })
})

export default router
