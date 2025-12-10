import * as arrow from 'apache-arrow'

function buildCaptchaError() {
  const error = new Error('captcha_required')
  error.code = 'captcha_required'
  return error
}

async function ensureCaptchaAllowed(response) {
  if (response.status !== 401) {
    return
  }
  let payload
  try {
    payload = await response.clone().json()
  } catch (_) {
    payload = null
  }
  if (payload?.error === 'captcha_required') {
    if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      window.dispatchEvent(new CustomEvent('captcha-required'))
    }
    throw buildCaptchaError()
  }
}

// Note: Arrow IPC compression (LZ4/ZSTD) is not available in apache-arrow 21.0.0
// because compressionRegistry is not exposed in the public API.
// The server sends uncompressed Arrow IPC streams instead.
// HTTP-level compression (Flask-Compress) will handle compression in production.

class ApiService {
  constructor(baseURL = '/api') {
    this.baseURL = baseURL
  }

  async fetchArrowData(endpoint, params = {}, retriesOrOptions = 3, retryDelay = 1000) {
    let method = 'GET'
    let retries = 3
    let retryDelayMs = typeof retryDelay === 'number' ? retryDelay : 1000
    if (typeof retriesOrOptions === 'object' && retriesOrOptions !== null) {
      method = (retriesOrOptions.method || 'GET').toUpperCase()
      retries = typeof retriesOrOptions.retries === 'number' ? retriesOrOptions.retries : 3
      if (typeof retriesOrOptions.retryDelay === 'number') {
        retryDelayMs = retriesOrOptions.retryDelay
      }
    } else {
      retries = typeof retriesOrOptions === 'number' ? retriesOrOptions : 3
    }

    let url = `${this.baseURL}${endpoint}`
    const fetchOptions = { method, headers: { Accept: 'application/vnd.apache.arrow.file' } }

    if (method === 'GET') {
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
    } else {
      fetchOptions.headers['Content-Type'] = 'application/json'
      fetchOptions.body = JSON.stringify(params || {})
    }

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const response = await fetch(url, fetchOptions)
        await ensureCaptchaAllowed(response)

        if (!response.ok) {
          if (response.status === 503) {
            const errorText = await response.text()
            if (attempt < retries && errorText.includes('reconnecting')) {
              await new Promise(resolve => setTimeout(resolve, retryDelayMs))
              continue
            }
            throw new Error(`Service unavailable: ${errorText}`)
          }
          const errorText = await response.text()
          console.error('Response error:', errorText)
          throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
        }

        const arrayBuffer = await response.arrayBuffer()
        const table = arrow.tableFromIPC(arrayBuffer)

        return table
      } catch (error) {
        if (attempt === retries || !error.message.includes('Service unavailable')) {
          console.error('Error fetching Arrow data:', error)
          throw error
        }

        await new Promise(resolve => setTimeout(resolve, retryDelayMs))
      }
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

  async getDimSignals() {
    return this.fetchArrowData('/dim-signals')
  }

  async getDimSignalsXd() {
    return this.fetchArrowData('/dim-signals-xd')
  }

  async getTravelTimeSummary(filters) {
    return this.fetchArrowData('/travel-time-summary', filters)
  }

  async getTravelTimeSummaryXd(filters) {
    return this.fetchArrowData('/travel-time-summary-xd', filters)
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

  async getAnomalySummaryXd(filters) {
    return this.fetchArrowData('/anomaly-summary-xd', filters)
  }

  async getAnomalyAggregated(filters, legendBy = null) {
    const params = { ...filters }
    if (legendBy && legendBy !== 'none') {
      params.legend_by = legendBy
    }
    return this.fetchArrowData('/anomaly-aggregated', params)
  }

  async getAnomalyByTimeOfDay(filters, legendBy = null) {
    const params = { ...filters }
    if (legendBy && legendBy !== 'none') {
      params.legend_by = legendBy
    }
    return this.fetchArrowData('/anomaly-by-time-of-day', params)
  }

  async getAnomalyPercentAggregated(filters, legendBy = null) {
    const params = { ...filters }
    if (legendBy && legendBy !== 'none') {
      params.legend_by = legendBy
    }
    return this.fetchArrowData('/anomaly-percent-aggregated', params)
  }

  async getAnomalyPercentByTimeOfDay(filters, legendBy = null) {
    const params = { ...filters }
    if (legendBy && legendBy !== 'none') {
      params.legend_by = legendBy
    }
    return this.fetchArrowData('/anomaly-percent-by-time-of-day', params)
  }

  async getTravelTimeData(filters) {
    return this.fetchArrowData('/travel-time-data', filters)
  }

  async getXdGeometry() {
    try {
      const arrowTable = await this.fetchArrowData('/xd-geometry')
      const rows = this.arrowTableToObjects(arrowTable)
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
      await ensureCaptchaAllowed(response)
      return response.json()
    } catch (error) {
      console.error('Health check failed:', error)
      throw error
    }
  }

  async getConnectionStatus() {
    try {
      const response = await fetch(`${this.baseURL}/connection-status`)
      await ensureCaptchaAllowed(response)
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

  // Before/After Comparison API Methods
  async getBeforeAfterSummary(beforeFilters, afterFilters, filters) {
    const params = {
      before_start_date: beforeFilters.start_date,
      before_end_date: beforeFilters.end_date,
      after_start_date: afterFilters.start_date,
      after_end_date: afterFilters.end_date,
      ...filters
    }
    return this.fetchArrowData('/before-after-summary', params)
  }

  async getBeforeAfterSummaryXd(beforeFilters, afterFilters, filters) {
    const params = {
      before_start_date: beforeFilters.start_date,
      before_end_date: beforeFilters.end_date,
      after_start_date: afterFilters.start_date,
      after_end_date: afterFilters.end_date,
      ...filters
    }
    return this.fetchArrowData('/before-after-summary-xd', params)
  }

  async getBeforeAfterAggregated(beforeFilters, afterFilters, filters, legendBy = null, isSmallMultiples = false) {
    const params = {
      before_start_date: beforeFilters.start_date,
      before_end_date: beforeFilters.end_date,
      after_start_date: afterFilters.start_date,
      after_end_date: afterFilters.end_date,
      ...filters
    }
    if (legendBy && legendBy !== 'none') {
      params.legend_by = legendBy
    }
    if (isSmallMultiples) {
      params.is_small_multiples = 'true'
    }
    return this.fetchArrowData('/before-after-aggregated', params)
  }

  async getBeforeAfterByTimeOfDay(beforeFilters, afterFilters, filters, legendBy = null, isSmallMultiples = false) {
    const params = {
      before_start_date: beforeFilters.start_date,
      before_end_date: beforeFilters.end_date,
      after_start_date: afterFilters.start_date,
      after_end_date: afterFilters.end_date,
      ...filters
    }
    if (legendBy && legendBy !== 'none') {
      params.legend_by = legendBy
    }
    if (isSmallMultiples) {
      params.is_small_multiples = 'true'
    }
    return this.fetchArrowData('/before-after-by-time-of-day', params)
  }

  // Changepoints API Methods
  async getChangepointMapSignals(filters) {
    return this.fetchArrowData('/changepoints-map-signals', filters, { method: 'POST' })
  }

  async getChangepointMapXd(filters) {
    return this.fetchArrowData('/changepoints-map-xd', filters, { method: 'POST' })
  }

  async getChangepointTable(filters) {
    return this.fetchArrowData('/changepoints-table', filters, { method: 'POST' })
  }

  async getChangepointDetail(params) {
    return this.fetchArrowData('/changepoints-detail', params)
  }

  async getMonitoringAnomalies(filters) {
    return this.fetchJson('/monitoring-anomalies', filters, { method: 'POST' })
  }

  async getConfig() {
    try {
      const response = await fetch(`${this.baseURL}/config`)
      await ensureCaptchaAllowed(response)
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

  async fetchJson(endpoint, params = {}, retriesOrOptions = 3, retryDelay = 1000) {
    let method = 'GET'
    let retries = 3
    let retryDelayMs = typeof retryDelay === 'number' ? retryDelay : 1000
    if (typeof retriesOrOptions === 'object' && retriesOrOptions !== null) {
      method = (retriesOrOptions.method || 'GET').toUpperCase()
      retries = typeof retriesOrOptions.retries === 'number' ? retriesOrOptions.retries : 3
      if (typeof retriesOrOptions.retryDelay === 'number') {
        retryDelayMs = retriesOrOptions.retryDelay
      }
    } else {
      retries = typeof retriesOrOptions === 'number' ? retriesOrOptions : 3
    }

    let url = `${this.baseURL}${endpoint}`
    const fetchOptions = { method, headers: {} }

    if (method === 'GET') {
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
        url += `?${searchParams.toString()}`
      }
    } else {
      fetchOptions.headers['Content-Type'] = 'application/json'
      fetchOptions.body = JSON.stringify(params || {})
    }

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const response = await fetch(url, fetchOptions)
        await ensureCaptchaAllowed(response)

        if (!response.ok) {
          if (response.status === 503 && attempt < retries) {
            await new Promise(resolve => setTimeout(resolve, retryDelayMs))
            continue
          }
          const errorText = await response.text()
          console.error('Response error:', errorText)
          throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
        }

        return await response.json()
      } catch (error) {
        if (attempt >= retries) {
          throw error
        }
        await new Promise(resolve => setTimeout(resolve, retryDelayMs))
      }
    }
  }

  async requestLoginLink(email) {
    const response = await fetch(`${this.baseURL}/auth/request-link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email })
    })

    await ensureCaptchaAllowed(response)
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.error || 'Failed to send login link')
    }

    return response.json()
  }

  async verifyLoginToken(token) {
    const response = await fetch(`${this.baseURL}/auth/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ token })
    })

    await ensureCaptchaAllowed(response)
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.error || 'Login link is invalid or expired')
    }

    return response.json()
  }

  async getCurrentSession() {
    const response = await fetch(`${this.baseURL}/auth/session`, {
      method: 'GET',
      credentials: 'include'
    })

    await ensureCaptchaAllowed(response)
    if (response.status === 401) {
      return { error: 'unauthenticated' }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.error || 'Failed to fetch session')
    }

    return response.json()
  }

  async logout() {
    const response = await fetch(`${this.baseURL}/auth/session`, {
      method: 'DELETE',
      credentials: 'include'
    })
    await ensureCaptchaAllowed(response)
  }

  async saveSubscription(settings) {
    const response = await fetch(`${this.baseURL}/subscriptions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ settings })
    })

    await ensureCaptchaAllowed(response)
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.error || 'Failed to save subscription')
    }

    return response.json()
  }

  async deleteSubscription() {
    const response = await fetch(`${this.baseURL}/subscriptions`, {
      method: 'DELETE',
      credentials: 'include'
    })

    await ensureCaptchaAllowed(response)
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.error || 'Failed to delete subscription')
    }

    return response.json()
  }

  async sendTestReport(settings) {
    const response = await fetch(`${this.baseURL}/reports/send-test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ settings })
    })

    await ensureCaptchaAllowed(response)
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.error || 'Failed to send test email')
    }

    return response.json()
  }

  async adminLogin(password) {
    const response = await fetch(`${this.baseURL}/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ password })
    })

    await ensureCaptchaAllowed(response)
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const error = new Error(payload.error || 'Failed to authenticate admin')
      error.code = payload?.error
      throw error
    }

    return payload
  }

  async fetchAdminTables() {
    const response = await fetch(`${this.baseURL}/admin/tables`, {
      method: 'GET',
      credentials: 'include'
    })

    await ensureCaptchaAllowed(response)
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const error = new Error(payload.error || 'Failed to fetch tables')
      error.code = payload?.error
      throw error
    }

    return payload
  }

  async runAdminQuery(sql) {
    const response = await fetch(`${this.baseURL}/admin/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ sql })
    })

    await ensureCaptchaAllowed(response)
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const error = new Error(payload.error || 'Query failed')
      error.code = payload?.error
      throw error
    }

    return payload
  }
}

export default new ApiService()
