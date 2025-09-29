import * as arrow from 'apache-arrow'

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

      console.log('Fetching Arrow data from:', url)
      
      const response = await fetch(url)
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('Response error:', errorText)
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
      }

      const arrayBuffer = await response.arrayBuffer()
      console.log('Received arrayBuffer size:', arrayBuffer.byteLength)
      
      const table = arrow.tableFromIPC(arrayBuffer)
      
      console.log('Arrow table columns:', table.schema.fields.map(f => f.name))
      console.log('Arrow table rows:', table.numRows)
      
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

  async getTravelTimeAggregated(filters) {
    return this.fetchArrowData('/travel-time-aggregated', filters)
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
      const response = await fetch(`${this.baseURL}/xd-geometry`)
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`)
      }
  return await response.json()
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
}

export default new ApiService()