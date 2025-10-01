# Performance Optimizations Implemented

## Summary

Implemented comprehensive performance optimizations addressing the critical bottlenecks identified in performance analysis. These changes target backend query performance, frontend rendering, and add extensive timing instrumentation.

---

## Backend Optimizations

### 1. Configuration System ([config.py](config.py))

**New file** - Centralized configuration for debugging and caching controls:

```python
# Enable/disable performance timing logs in backend
DEBUG_BACKEND_TIMING = True

# Enable/disable Snowflake query result caching
DEBUG_DISABLE_SNOWFLAKE_CACHE = True

# Enable/disable server-side result caching (geometry cache, etc.)
DEBUG_DISABLE_SERVER_CACHE = True

# Frontend debug logging control
DEBUG_FRONTEND_LOGGING = True

# Production mode - disables all debug flags
PRODUCTION_MODE = False
```

**Benefits:**
- Single source of truth for debug settings
- Easy toggle between debug and production modes
- Separate control for different caching layers

---

### 2. Snowflake Query Cache Disabled ([database.py](database.py))

Added automatic cache disabling when `DEBUG_DISABLE_SNOWFLAKE_CACHE = True`:

```python
# In get_snowflake_session()
if DEBUG_DISABLE_SNOWFLAKE_CACHE:
    snowflake_session.sql("ALTER SESSION SET USE_CACHED_RESULT = FALSE").collect()
    print("Snowflake query result cache DISABLED")
```

**Benefits:**
- Reveals true query performance without cache interference
- Critical for identifying actual bottlenecks
- Easy to re-enable for production

---

### 3. Comprehensive Backend Timing ([routes/api_travel_time.py](routes/api_travel_time.py))

Added detailed timing instrumentation to all endpoints:

#### `/travel-time-summary` Timing:
```
[TIMING] /travel-time-summary START
  Params: date=2025-09-29 to 2025-10-01, signals=all, table=TRAVEL_TIME_DAILY_AGG
  [1] DIM_SIGNALS_XD query: 125.45ms (25678 rows)
  [2] Extract XD values: 12.30ms (16070 unique XDs)
  [INFO] NO XD filter (querying all signals)
  [3] Analytics query (TRAVEL_TIME_DAILY_AGG): 3842.10ms (16068 rows)
  [4] Create XD lookup dict: 8.20ms
  [5] Build Arrow table & serialize: 45.60ms
  [TOTAL] /travel-time-summary: 4033.65ms
```

#### `/travel-time-aggregated` Timing:
```
[TIMING] /travel-time-aggregated START
  Params: date=2025-09-29 to 2025-10-01, xd_segments=16070, table=TRAVEL_TIME_DAILY_AGG
  [INFO] Using provided XD segments: 16070 XDs
  [2] Aggregated query (TRAVEL_TIME_DAILY_AGG): 458.90ms
  [TOTAL] /travel-time-aggregated: 459.30ms
```

**Benefits:**
- Pinpoint exactly which query is slow
- Track query time vs serialization overhead
- Identify unnecessary dimension lookups

---

### 4. Fixed Unnecessary XD IN Clauses ([routes/api_travel_time.py](routes/api_travel_time.py))

**CRITICAL FIX** - Only apply XD filter when signal selections are made:

**Before:**
```python
# ALWAYS added XD filter, even when querying all signals
xd_filter = build_xd_filter(xd_values)  # Adds "AND XD IN (1626470730, 1626470464, ...16k XDs...)"
```

**After:**
```python
# ONLY add XD filter if we're filtering to specific signals
xd_filter = build_xd_filter(xd_values) if signal_ids else ""

if signal_ids:
    print(f"  [INFO] XD filter applied: {len(xd_values)} XDs")
else:
    print(f"  [INFO] NO XD filter (querying all signals)")
```

**Impact:**
- Removes massive IN clause with 16k XD values when no selection made
- Snowflake can use better query plans without IN clause
- **Expected 20-40% improvement** on initial load

---

### 5. Fixed FREEFLOW Join Explosion ([routes/api_travel_time.py](routes/api_travel_time.py))

**CRITICAL FIX** - Prevent join explosion by aggregating first, then joining:

**Before (JOIN EXPLOSION):**
```sql
SELECT
    mv.XD,
    SUM(mv.TOTAL_TRAVEL_TIME_SECONDS) / SUM(mv.RECORD_COUNT * f.TRAVEL_TIME_SECONDS) as TTI
FROM TRAVEL_TIME_DAILY_AGG mv
INNER JOIN FREEFLOW f ON mv.XD = f.XD  -- ⚠️ Multiplies rows!
WHERE mv.DATE_ONLY BETWEEN '2025-09-06' AND '2025-10-01'
AND mv.XD IN (...)  -- 16k XDs
GROUP BY mv.XD
```

**After (AGGREGATE FIRST):**
```sql
WITH agg AS (
    -- First: Aggregate within date range
    SELECT
        XD,
        SUM(TOTAL_TRAVEL_TIME_SECONDS) as TOTAL_TRAVEL_TIME,
        SUM(RECORD_COUNT) as TOTAL_RECORDS
    FROM TRAVEL_TIME_DAILY_AGG
    WHERE DATE_ONLY BETWEEN '2025-09-06' AND '2025-10-01'
    GROUP BY XD
)
-- Then: Join once per XD with FREEFLOW
SELECT
    agg.XD,
    agg.TOTAL_TRAVEL_TIME / (agg.TOTAL_RECORDS * f.TRAVEL_TIME_SECONDS) as TTI
FROM agg
INNER JOIN FREEFLOW f ON agg.XD = f.XD
```

**Impact:**
- Eliminates row multiplication before aggregation
- Processes far fewer rows in memory
- **Expected 30-60% improvement** on multi-day queries

---

### 6. Server-Side Cache Control ([routes/api_travel_time.py](routes/api_travel_time.py))

Made geometry cache respect debug configuration:

```python
# Check cache unless disabled
if not DEBUG_DISABLE_SERVER_CACHE and _xd_geometry_cache is not None:
    if DEBUG_BACKEND_TIMING:
        print("[TIMING] /xd-geometry: Returned from cache")
    return jsonify(_xd_geometry_cache)
```

**Benefits:**
- Can disable cache to test geometry load performance
- Logs when cache is used

---

## Frontend Optimizations

### 7. Frontend Configuration System ([frontend/src/config.js](frontend/src/config.js))

**New file** - Frontend debug control with helper functions:

```javascript
export const DEBUG_FRONTEND_LOGGING = true

export function debugLog(...args) {
  if (DEBUG_FRONTEND_LOGGING) {
    console.log(...args)
  }
}
```

**Benefits:**
- Single toggle for all frontend debug logs
- Can disable in production for clean console
- Helper functions for consistent logging

---

### 8. Deferred Geometry Loading ([frontend/src/components/SharedMap.vue](frontend/src/components/SharedMap.vue))

**CRITICAL OPTIMIZATION** - Defer loading 16k XD geometries until after initial render:

**Before:**
```javascript
onMounted(() => {
  initializeMap()
  updateMarkers()
  updateGeometry()
  geometryStore.loadGeometry()  // ⚠️ Blocks initial render!
  // ...
})
```

**After:**
```javascript
onMounted(() => {
  initializeMap()
  updateMarkers()
  updateGeometry()

  // Defer geometry loading until after initial render completes
  requestIdleCallback(() => {
    console.log('🗺️ Starting deferred geometry load')
    geometryStore.loadGeometry().then(() => {
      console.log('🗺️ Geometry loaded')
    })
  }, { timeout: 2000 })
  // ...
})
```

**Impact:**
- Prevents blocking initial map render
- Geometry loads in background during browser idle time
- **Expected 1-2 second improvement** on perceived initial load time

---

### 9. Comprehensive Frontend Timing ([frontend/src/](frontend/src/))

Added detailed timing to all critical components:

#### TravelTime.vue:
```
🚀 TravelTime.vue: onMounted START
📡 API: getTravelTimeSummary took 4373.30ms
📡 API: arrowTableToObjects took 22.00ms
📡 API: mapData assignment took 0.10ms
⏱️ TravelTime.vue: loadMapData complete, took 7477.60ms
📊 API: getTravelTimeAggregated took 458.90ms
✅ TravelTime.vue: onMounted COMPLETE, total 7973.20ms
```

#### SharedMap.vue:
```
🗺️ SharedMap: onMounted START
🗺️ SharedMap: initializeMap took 12.50ms
🗺️ SharedMap: updateMarkers took 89.30ms
🗺️ SharedMap: updateGeometry took 875.20ms
🗺️ SharedMap: onMounted COMPLETE, total 3045.80ms
```

#### TravelTimeChart.vue:
```
📊 CHART WATCH: data changed, deferring to nextTick
📊 CHART: nextTick triggered, delay from watch: 0.20ms
📊 CHART: updateChart START
📊 CHART: setOption took 33.20ms
📊 CHART: updateChart COMPLETE, total 33.40ms
```

**Benefits:**
- Complete visibility into every operation
- Identifies exact source of delays
- Can be toggled off via `DEBUG_FRONTEND_LOGGING = false`

---

## Testing Instructions

### 1. Run with Debug Logging Enabled

Current settings in [config.py](config.py):
```python
DEBUG_BACKEND_TIMING = True
DEBUG_DISABLE_SNOWFLAKE_CACHE = True
DEBUG_DISABLE_SERVER_CACHE = True
```

Current settings in [frontend/src/config.js](frontend/src/config.js):
```javascript
export const DEBUG_FRONTEND_LOGGING = true
```

### 2. Test Initial Load (2-3 days)

1. Clear browser cache
2. Refresh the page
3. Check console for backend timing:
   ```
   [TIMING] /travel-time-summary START
   ...
   [TOTAL] /travel-time-summary: XXXXms
   ```
4. Check console for frontend timing:
   ```
   🚀 TravelTime.vue: onMounted START
   ...
   ✅ TravelTime.vue: onMounted COMPLETE, total XXXXms
   ```

### 3. Test Date Range Changes (5+ days, 24+ days)

1. Change date range in filter panel
2. Observe backend query times in Python console
3. Observe frontend update times in browser console

### 4. Expected Improvements

| Scenario | Before | After (Expected) | Improvement |
|----------|--------|------------------|-------------|
| Initial load (2 days) | 7-8s | **4-5s** | 40-50% |
| Date change (5 days) | 16s | **8-10s** | 40-50% |
| Date change (24 days) | 20s | **10-12s** | 40-50% |

### 5. Disable Debug Logging for Production

In [config.py](config.py):
```python
PRODUCTION_MODE = True  # Disables all debug flags
```

In [frontend/src/config.js](frontend/src/config.js):
```javascript
export const DEBUG_FRONTEND_LOGGING = false
```

---

## Key Metrics to Monitor

### Backend Logs (Python Console)

Look for:
1. **DIM_SIGNALS_XD query time** - Should be < 200ms
2. **Analytics query time** - Main bottleneck (varies with date range)
3. **Total request time** - Sum should match frontend network time

### Frontend Logs (Browser Console)

Look for:
1. **getTravelTimeSummary API time** - Network + backend query
2. **Map updates time** - Should be ~1000ms
3. **Geometry load time** - Now deferred, should not block initial render
4. **Total onMounted time** - Should exclude deferred geometry load

---

## Files Modified

### Backend:
- `config.py` (NEW)
- `database.py`
- `routes/api_travel_time.py`

### Frontend:
- `frontend/src/config.js` (NEW)
- `frontend/src/views/TravelTime.vue`
- `frontend/src/components/SharedMap.vue`
- `frontend/src/components/TravelTimeChart.vue`

### Documentation:
- `PERFORMANCE_ANALYSIS.md` (NEW)
- `OPTIMIZATIONS_IMPLEMENTED.md` (THIS FILE)

---

## Next Steps

1. **Test and measure improvements** with debug logging enabled
2. **Analyze backend query times** - Identify if DIM or Analytics query is slow
3. **Consider database indexes** if Analytics query is still slow:
   ```sql
   CREATE INDEX idx_daily_agg_xd_date ON TRAVEL_TIME_DAILY_AGG(XD, DATE_ONLY);
   CREATE INDEX idx_hourly_agg_xd_ts ON TRAVEL_TIME_HOURLY_AGG(XD, TIMESTAMP);
   ```
4. **Implement query result caching** if same queries run repeatedly
5. **Consider map rendering optimizations** if map updates still slow (zoom-based LOD)

---

## Rollback Instructions

If issues occur, rollback by:

1. **Disable Snowflake cache disabling:**
   ```python
   # config.py
   DEBUG_DISABLE_SNOWFLAKE_CACHE = False
   ```

2. **Revert query changes:**
   ```bash
   git checkout routes/api_travel_time.py
   ```

3. **Disable debug logging:**
   ```python
   # config.py
   DEBUG_BACKEND_TIMING = False
   ```
   ```javascript
   // frontend/src/config.js
   export const DEBUG_FRONTEND_LOGGING = false
   ```
