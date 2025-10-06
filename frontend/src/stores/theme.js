import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  // Load saved theme from localStorage, default to 'light'
  const savedTheme = localStorage.getItem('theme') || 'light'
  const currentTheme = ref(savedTheme)

  // Persist theme changes to localStorage
  watch(currentTheme, (newTheme) => {
    localStorage.setItem('theme', newTheme)
  })

  function toggleTheme() {
    currentTheme.value = currentTheme.value === 'light' ? 'dark' : 'light'
  }

  function setTheme(theme) {
    if (theme === 'light' || theme === 'dark') {
      currentTheme.value = theme
    }
  }

  return {
    currentTheme,
    toggleTheme,
    setTheme
  }
})
