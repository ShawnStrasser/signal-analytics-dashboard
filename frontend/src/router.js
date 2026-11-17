import { createRouter, createWebHistory } from 'vue-router'
// Route-level code splitting: each page (and its heavy deps such as ECharts,
// Leaflet, canvas-confetti) loads only when first visited.
const TravelTime = () => import('./views/TravelTime.vue')
const Anomalies = () => import('./views/Anomalies.vue')
const BeforeAfter = () => import('./views/BeforeAfter.vue')
const Changepoints = () => import('./views/Changepoints.vue')
const Monitoring = () => import('./views/Monitoring.vue')
const Admin = () => import('./views/Admin.vue')
const Captcha = () => import('./views/Captcha.vue')
const NotFound = () => import('./views/NotFound.vue')
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

// A tab left open across a deploy may request a lazy chunk whose hashed filename
// no longer exists. Reload once to pick up the new index.html instead of hanging.
const CHUNK_ERROR_PATTERN = /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|ChunkLoadError/i
router.onError((error, to) => {
  if (typeof window === 'undefined' || !CHUNK_ERROR_PATTERN.test(String(error?.message || error))) {
    return
  }
  try {
    const key = 'chunk-reload-at'
    const last = Number(sessionStorage.getItem(key) || 0)
    if (Date.now() - last < 10000) return // avoid reload loops
    sessionStorage.setItem(key, String(Date.now()))
  } catch (e) {
    // sessionStorage unavailable; fall through to a single reload
  }
  window.location.assign(to?.fullPath || window.location.href)
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
