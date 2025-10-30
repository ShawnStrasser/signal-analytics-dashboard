import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import ApiService from '@/services/api'

export const useAuthStore = defineStore('auth', () => {
  const email = ref(null)
  const subscribed = ref(false)
  const settings = ref(null)
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(email.value))

  function clearSession() {
    email.value = null
    subscribed.value = false
    settings.value = null
  }

  async function fetchSession() {
    loading.value = true
    try {
      const session = await ApiService.getCurrentSession()
      if (session && !session.error) {
        email.value = session.email
        subscribed.value = Boolean(session.subscribed)
        settings.value = session.settings || null
      } else {
        clearSession()
      }
    } catch {
      clearSession()
    } finally {
      loading.value = false
    }
  }

  async function requestLoginLink(emailAddress) {
    return ApiService.requestLoginLink(emailAddress)
  }

  async function verifyToken(token) {
    const session = await ApiService.verifyLoginToken(token)
    email.value = session.email
    subscribed.value = Boolean(session.subscribed)
    settings.value = session.settings || null
    return session
  }

  async function subscribe(settingsPayload) {
    const result = await ApiService.saveSubscription(settingsPayload)
    subscribed.value = true
    settings.value = result.settings || settingsPayload
    return result
  }

  async function unsubscribe() {
    await ApiService.deleteSubscription()
    subscribed.value = false
    // Keep email so UI still knows user is logged in
  }

  async function sendTestEmail(settingsPayload) {
    return ApiService.sendTestReport(settingsPayload)
  }

  async function logout() {
    await ApiService.logout()
    clearSession()
  }

  return {
    email,
    subscribed,
    settings,
    loading,
    isAuthenticated,
    fetchSession,
    requestLoginLink,
    verifyToken,
    subscribe,
    unsubscribe,
    sendTestEmail,
    logout
  }
})
