import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { promises as fs } from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'
import { promisify } from 'node:util'

const brotli = promisify(zlib.brotliCompress)
const gzip = promisify(zlib.gzip)

/**
 * Pre-compress built JS/CSS/SVG assets (.br + .gz) so Flask can serve them
 * directly with Content-Encoding instead of compressing on every request.
 */
function precompressAssets() {
  let outDir
  return {
    name: 'precompress-assets',
    apply: 'build',
    configResolved(config) {
      outDir = path.resolve(config.root, config.build.outDir)
    },
    async closeBundle() {
      const assetsDir = path.join(outDir, 'assets')
      let files = []
      try {
        files = await fs.readdir(assetsDir)
      } catch {
        return
      }
      await Promise.all(
        files
          .filter((f) => /\.(js|css|svg)$/.test(f))
          .map(async (f) => {
            const full = path.join(assetsDir, f)
            const buf = await fs.readFile(full)
            if (buf.length < 1024) return
            const [br, gz] = await Promise.all([
              brotli(buf, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 11 } }),
              gzip(buf, { level: 9 })
            ])
            await Promise.all([fs.writeFile(`${full}.br`, br), fs.writeFile(`${full}.gz`, gz)])
          })
      )
    }
  }
}

export default defineConfig({
  plugins: [
    vue(),
    vuetify({
      autoImport: true,
    }),
    precompressAssets(),
  ],
  envPrefix: ['VITE_', 'APP_'],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        // Stable vendor chunks so app-code changes don't invalidate cached libraries
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('echarts') || id.includes('zrender')) return 'vendor-echarts'
          if (id.includes('leaflet')) return 'vendor-leaflet'
          if (id.includes('apache-arrow') || id.includes('flatbuffers')) return 'vendor-arrow'
          if (id.includes('canvas-confetti')) return 'vendor-confetti'
          if (id.includes('vuetify')) return 'vendor-vuetify'
          if (id.includes('/vue') || id.includes('pinia') || id.includes('@vue')) return 'vendor-vue'
          return 'vendor'
        }
      }
    }
  },
  resolve: {
    alias: {
      '@': '/src',
    },
  },
})
