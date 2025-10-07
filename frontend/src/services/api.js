import * as arrow from 'apache-arrow'

// Note: Arrow IPC compression (LZ4/ZSTD) is not available in apache-arrow 21.0.0
// because compressionRegistry is not exposed in the public API.
// The server sends uncompressed Arrow IPC streams instead.
// HTTP-level compression (Flask-Compress) will handle compression in production.

class ApiService {
  constructor(baseURL = '/api') {
    this.baseURL = baseURL
  }

  async fetchArrowData(endpoint, params = {}) {
    try {
      // Simple URL construction that works with Vite proxy
      let url = `${this.baseURL}${endpoint}`
      
      // Add query parameters
      const searchParams = new URLSearchParams()
      Object.keys(params).forEach(key => {
        const value = params[key]
        if (value !== null && value !== undefined) {
          if (Array.isArray(value)) {
            value.forEach(v => searchParams.append(key, v))
          } else {
            searchParams.append(key, value)
          }
        }
      })
      
      if (searchParams.toString()) {
        url += '?' + searchParams.toString()
      }

      const response = await fetch(url)

      if (!response.ok) {
        const errorText = await response.text()
        console.error('Response error:', errorText)
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
      }

      const arrayBuffer = await response.arrayBuffer()
      const table = arrow.tableFromIPC(arrayBuffer)
      
      return table
    } catch (error) {
      console.error('Error fetching Arrow data:', error)
      throw error
    }
  }

  // Convert Arrow table to JavaScript objects for easier manipulation
  arrowTableToObjects(table) {
    const objects = []
    const fields = table.schema.fields
    const columns = fields.map(field => table.getChild(field.name))

    for (let rowIndex = 0; rowIndex < table.numRows; rowIndex++) {
      const obj = {}

      columns.forEach((column, colIndex) => {
        const fieldName = fields[colIndex].name
        let value = column.get(rowIndex)

        if (value === null || value === undefined) {
          obj[fieldName] = value
          return
        }

        if (typeof value === 'bigint') {
          const numericValue = Number(value)
          obj[fieldName] = Number.isSafeInteger(numericValue) ? numericValue : value.toString()
          return
        }

        if (value instanceof Date) {
          obj[fieldName] = value.toISOString()
          return
        }

        obj[fieldName] = value
      })

      objects.push(obj)
    }

    return objects
  }

  // Signal Analytics API Methods
  async getSignals() {
    return this.fetchArrowData('/signals')
  }

  async getTravelTimeSummary(filters) {
    return this.fetchArrowData('/travel-time-summary', filters)
  }

  async getTravelTimeAggregated(filters, legendBy = null) {
    const params = { ...filters }
    if (legendBy && legendBy !== 'none') {
      params.legend_by = legendBy
    }
    return this.fetchArrowData('/travel-time-aggregated', params)
  }

  async getTravelTimeByTimeOfDay(filters, legendBy = null) {
    const params = { ...filters }
    if (legendBy && legendBy !== 'none') {
      params.legend_by = legendBy
    }
    return this.fetchArrowData('/travel-time-by-time-of-day', params)
  }

  async getAnomalySummary(filters) {
    return this.fetchArrowData('/anomaly-summary', filters)
  }

  async getAnomalyAggregated(filters) {
    return this.fetchArrowData('/anomaly-aggregated', filters)
  }

  async getTravelTimeData(filters) {
    return this.fetchArrowData('/travel-time-data', filters)
  }

  async getXdGeometry() {
    try {
      const t0 = performance.now()

      // Fetch Arrow data instead of JSON
      const arrowTable = await this.fetchArrowData('/xd-geometry')
      const t1 = performance.now()
      console.log(`📍 API: fetchArrowData took ${(t1 - t0).toFixed(2)}ms`)

      // Convert Arrow table to objects
      const rows = this.arrowTableToObjects(arrowTable)
      const t2 = performance.now()
      console.log(`📍 API: arrowTableToObjects took ${(t2 - t1).toFixed(2)}ms`)

      // Parse GeoJSON strings and build FeatureCollection
      const parseStart = performance.now()
      const features = []

      for (const row of rows) {
        if (!row.GEOJSON) continue

        try {
          const geometry = JSON.parse(row.GEOJSON)
          features.push({
            type: 'Feature',
            properties: { XD: row.XD },
            geometry: geometry
          })
        } catch (e) {
          console.warn(`Failed to parse GeoJSON for XD ${row.XD}:`, e)
        }
      }

      const t3 = performance.now()
      console.log(`📍 API: GeoJSON parsing took ${(t3 - parseStart).toFixed(2)}ms (${features.length} features)`)
      console.log(`📍 API: getXdGeometry TOTAL ${(t3 - t0).toFixed(2)}ms`)

      return {
        type: 'FeatureCollection',
        features: features
      }
    } catch (error) {
      console.error('Error fetching XD geometry:', error)
      throw error
    }
  }

  async healthCheck() {
    try {
      const response = await fetch(`${this.baseURL}/health`)
      return response.json()
    } catch (error) {
      console.error('Health check failed:', error)
      throw error
    }
  }

  async getConnectionStatus() {
    try {
      const response = await fetch(`${this.baseURL}/connection-status`)
      return response.json()
    } catch (error) {
      console.error('Connection status check failed:', error)
      return { connected: false, connecting: false, error: error.message }
    }
  }

  async waitForConnection(maxAttempts = 15, delayMs = 2000) {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const health = await this.healthCheck()
        if (health.database_connected) {
          return true
        }

        // If still connecting, wait and try again
        if (health.connecting) {
          await new Promise(resolve => setTimeout(resolve, delayMs))
          continue
        }

        // If not connected and not connecting, return false
        return false
      } catch (error) {
        // Network error, wait and retry
        if (attempt < maxAttempts - 1) {
          await new Promise(resolve => setTimeout(resolve, delayMs))
        }
      }
    }
    return false
  }

  async getConfig() {
    try {
      const response = await fetch(`${this.baseURL}/config`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      return await response.json()
    } catch (error) {
      console.error('Error fetching config:', error)
      // Return default values if config fetch fails
      return { maxLegendEntities: 10 }
    }
  }
}

export default new ApiService()