import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import router from './router'
import App from './App.vue'
import { isCaptchaVerified } from './utils/captchaSession'

// Vuetify
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

// Leaflet CSS
import 'leaflet/dist/leaflet.css'

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'light',
    themes: {
      light: {
        colors: {
          primary: '#1976D2',
          secondary: '#424242',
          accent: '#82B1FF',
          error: '#FF5252',
          info: '#2196F3',
          success: '#4CAF50',
          warning: '#FFC107',
        },
      },
      dark: {
        dark: true,
        colors: {
          primary: '#2196F3',
          secondary: '#616161',
          accent: '#82B1FF',
          error: '#FF5252',
          info: '#2196F3',
          success: '#4CAF50',
          warning: '#FFC107',
          background: '#121212',
          surface: '#1E1E1E',
        },
      },
    },
  },
})

const pinia = createPinia()
const app = createApp(App)

app.use(pinia)
app.use(router)
app.use(vuetify)

const bootstrap = async () => {
  await router.isReady()
  if (!isCaptchaVerified() && router.currentRoute.value.name !== 'Captcha') {
    const redirectTarget = router.currentRoute.value.fullPath
    await router.replace({
      name: 'Captcha',
      query: redirectTarget && redirectTarget !== '/captcha' ? { redirect: redirectTarget } : {}
    }).catch(() => {})
  }
  app.mount('#app')
}

bootstrap()
