/**
 * CARTO raster basemap URL helper.
 *
 * CARTO raster tiles require an API key passed as `?key=`. The key is a prod-only
 * runtime env var (CARTO_KEY) which the Flask server injects into index.html as
 * window.__APP_CONFIG__.cartoKey, so it never has to be baked into the build.
 * Without a key, CARTO serves "API KEY REQUIRED" watermark tiles (e.g. in dev).
 */

export function getCartoKey() {
  if (typeof window === 'undefined') return ''
  const key = window.__APP_CONFIG__?.cartoKey
  return typeof key === 'string' ? key.trim() : ''
}

export function cartoTileUrl(style) {
  const base = `https://{s}.basemaps.cartocdn.com/${style}/{z}/{x}/{y}.png`
  const key = getCartoKey()
  return key ? `${base}?key=${encodeURIComponent(key)}` : base
}

export const CARTO_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> ' +
  '&copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>'
