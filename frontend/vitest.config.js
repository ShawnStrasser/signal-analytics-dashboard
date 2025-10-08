import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [
    vue(),
    vuetify({
      autoImport: true,
    }),
  ],
  test: {
    // Use jsdom for DOM simulation (alternative: happy-dom for faster tests)
    environment: 'jsdom',

    // Global test setup
    globals: true,

    // Enable coverage reporting
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/**',
        'src/test-utils/**',
        '**/*.test.js',
        '**/*.spec.js',
      ]
    },

    // Setup files to run before each test file
    setupFiles: [],

    // Increase timeout for tests that might need more time
    testTimeout: 10000,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
