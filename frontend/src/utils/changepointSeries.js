export function normalizeChangepointDetailRow(row = {}) {
  const timestamp = row.TIMESTAMP ?? row.timestamp ?? null
  const travelTime = row.TRAVEL_TIME_SECONDS ?? row.travel_time_seconds ?? 0
  const periodRaw = row.PERIOD ?? row.period ?? ''

  return {
    timestamp,
    travel_time_seconds: Number(travelTime) || 0,
    period: String(periodRaw).toLowerCase()
  }
}

export function buildChangepointDateSeries(rows = []) {
  const before = []
  const after = []

  rows.forEach((row) => {
    if (!row?.timestamp) {
      return
    }
    const y = Number(row.travel_time_seconds)
    if (!Number.isFinite(y)) {
      return
    }

    const parsed = new Date(row.timestamp)
    const x = parsed.getTime()
    if (!Number.isFinite(x)) {
      return
    }

    const point = [x, Number(y.toFixed(2))]
    if (row.period === 'before') {
      before.push(point)
    } else if (row.period === 'after') {
      after.push(point)
    }
  })

  before.sort((a, b) => a[0] - b[0])
  after.sort((a, b) => a[0] - b[0])

  return { before, after }
}

export function buildChangepointTimeOfDaySeries(rows = []) {
  const beforeBuckets = new Map()
  const afterBuckets = new Map()

  rows.forEach((row) => {
    if (!row?.timestamp) {
      return
    }
    const value = Number(row.travel_time_seconds)
    if (!Number.isFinite(value)) {
      return
    }

    const date = new Date(row.timestamp)
    const minutes = date.getHours() * 60 + date.getMinutes()
    const bucketMap = row.period === 'before' ? beforeBuckets : afterBuckets
    const existing = bucketMap.get(minutes) || { sum: 0, count: 0 }
    bucketMap.set(minutes, {
      sum: existing.sum + value,
      count: existing.count + 1
    })
  })

  const toSeries = (bucketMap) => Array.from(bucketMap.entries())
    .map(([minutes, stats]) => {
      const avg = stats.count > 0 ? stats.sum / stats.count : 0
      return [minutes, Number(avg.toFixed(2))]
    })
    .sort((a, b) => a[0] - b[0])

  return {
    before: toSeries(beforeBuckets),
    after: toSeries(afterBuckets)
  }
}
