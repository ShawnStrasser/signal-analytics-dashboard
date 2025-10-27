import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  // Load saved theme from localStorage, default to 'light'
  const savedTheme = localStorage.getItem('theme') || 'light'
  const currentTheme = ref(savedTheme)

  // Load saved colorblind mode from localStorage, default to false
  const savedColorblindMode = localStorage.getItem('colorblindMode') === 'true'
  const colorblindMode = ref(savedColorblindMode)

  // Persist theme changes to localStorage
  watch(currentTheme, (newTheme) => {
    localStorage.setItem('theme', newTheme)
  })

  // Persist colorblind mode changes to localStorage
  watch(colorblindMode, (newMode) => {
    localStorage.setItem('colorblindMode', String(newMode))
  })

  function toggleTheme() {
    currentTheme.value = currentTheme.value === 'light' ? 'dark' : 'light'
  }

  function setTheme(theme) {
    if (theme === 'light' || theme === 'dark') {
      currentTheme.value = theme
    }
  }

  function toggleColorblindMode() {
    colorblindMode.value = !colorblindMode.value
  }

  function setColorblindMode(enabled) {
    colorblindMode.value = Boolean(enabled)
  }

  return {
    currentTheme,
    toggleTheme,
    setTheme,
    colorblindMode,
    toggleColorblindMode,
    setColorblindMode
  }
})
