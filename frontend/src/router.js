import { createRouter, createWebHistory } from 'vue-router'
import TravelTime from './views/TravelTime.vue'
import Anomalies from './views/Anomalies.vue'
import BeforeAfter from './views/BeforeAfter.vue'
import Changepoints from './views/Changepoints.vue'
import Monitoring from './views/Monitoring.vue'
import Admin from './views/Admin.vue'
import Captcha from './views/Captcha.vue'
import NotFound from './views/NotFound.vue'
import { fetchCaptchaStatus, isCaptchaVerifiedCached, resetCaptchaCache } from './utils/captchaSession'

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
  },
  {
    path: '/admin',
    name: 'Admin',
    component: Admin,
    meta: { showFilters: false }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: NotFound,
    meta: { showFilters: false }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

let pendingCaptchaCheck = null

async function ensureCaptchaVerified() {
  if (typeof window === 'undefined') {
    return true
  }
  if (isCaptchaVerifiedCached()) {
    return true
  }
  if (!pendingCaptchaCheck) {
    pendingCaptchaCheck = fetchCaptchaStatus()
      .then(result => !!result?.verified)
      .catch(error => {
        console.warn('Captcha status check failed', error)
        return false
      })
      .finally(() => {
        pendingCaptchaCheck = null
      })
  }
  return pendingCaptchaCheck
}

router.beforeEach(async to => {
  if (to.meta?.skipCaptcha) {
    return true
  }
  const verified = await ensureCaptchaVerified()
  if (verified) {
    return true
  }

  const fallbackPath = '/travel-time'
  let redirectTarget = to.fullPath || fallbackPath

  if (redirectTarget === '/' || redirectTarget === '/captcha') {
    redirectTarget = fallbackPath
  }

  return {
    name: 'Captcha',
    query: { redirect: redirectTarget }
  }
})

if (typeof window !== 'undefined') {
  window.addEventListener('captcha-required', () => {
    resetCaptchaCache()
    pendingCaptchaCheck = null
    const currentRoute = router.currentRoute.value
    if (currentRoute?.name === 'Captcha') {
      return
    }
    const fallbackPath = '/travel-time'
    let redirectTarget = currentRoute?.fullPath || fallbackPath
    if (redirectTarget === '/' || redirectTarget === '/captcha') {
      redirectTarget = fallbackPath
    }
    router
      .replace({
        name: 'Captcha',
        query: { redirect: redirectTarget },
      })
      .catch(() => {})
  })
}

export default router
