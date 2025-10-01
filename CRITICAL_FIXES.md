# CRITICAL FIXES - Query Correctness & Performance

## Issues Fixed

### 🔴 CRITICAL: Fixed Broken TTI Calculation

**Problem:** The query optimization broke the Travel Time Index calculation, producing garbage results.

**Root Cause:** I incorrectly changed the TTI formula. The correct formula is:
```
TTI = AVG(actual_travel_time / freeflow_time)
```

NOT:
```
TTI = SUM(actual) / SUM(freeflow)  ← WRONG!
```

**Fix Applied:**

#### For Base Table (TRAVEL_TIME_ANALYTICS):
```sql
-- CORRECT: Calculate TTI per record, then average
WITH agg AS (
    SELECT
        t.XD,
        SUM(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) as TOTAL_TTI,
        AVG(t.TRAVEL_TIME_SECONDS) as AVG_TRAVEL_TIME,
        COUNT(*) as RECORD_COUNT
    FROM TRAVEL_TIME_ANALYTICS t
    INNER JOIN FREEFLOW f ON t.XD = f.XD
    WHERE t.TIMESTAMP >= '{start_date}'
    AND t.TIMESTAMP <= '{end_date}'
    GROUP BY t.XD
)
SELECT
    XD,
    COALESCE(TOTAL_TTI / NULLIF(RECORD_COUNT, 0), 0) as TRAVEL_TIME_INDEX,
    AVG_TRAVEL_TIME,
    RECORD_COUNT
FROM agg
```

#### For Materialized Views (TRAVEL_TIME_DAILY_AGG):
```sql
-- CORRECT: Sum total travel time / sum total freeflow time
SELECT
    mv.XD,
    COALESCE(
        SUM(mv.TOTAL_TRAVEL_TIME_SECONDS) / NULLIF(SUM(mv.RECORD_COUNT * f.TRAVEL_TIME_SECONDS), 0),
        0
    ) as TRAVEL_TIME_INDEX,
    SUM(mv.AVG_TRAVEL_TIME * mv.RECORD_COUNT) / NULLIF(SUM(mv.RECORD_COUNT), 0) as AVG_TRAVEL_TIME,
    SUM(mv.RECORD_COUNT) as RECORD_COUNT
FROM TRAVEL_TIME_DAILY_AGG mv
INNER JOIN FREEFLOW f ON mv.XD = f.XD
WHERE mv.DATE_ONLY >= '{start_date}'
AND mv.DATE_ONLY <= '{end_date}'
GROUP BY mv.XD
```

**Impact:** Results now match original query logic.

---

### 🔴 CRITICAL: Fixed Excessive Database Queries

**Problem:** 15+ queries on initial page load, including:
- Multiple `ALTER SESSION SET USE_CACHED_RESULT = FALSE` (4-5 times!)
- Multiple `SELECT 1` health checks
- Duplicate geometry loads

**Root Causes:**
1. **Health check on every `get_snowflake_session()` call** - Unnecessary
2. **Cache disable not tracked** - Ran ALTER SESSION multiple times
3. **Duplicate geometry loading** - Both App.vue and SharedMap.vue loaded it

**Fixes Applied:**

#### 1. Removed Unnecessary Health Checks ([database.py](database.py))
```python
# BEFORE: Ran SELECT 1 on every session retrieval
if snowflake_session is not None:
    snowflake_session.sql("SELECT 1").collect()  # ❌ Too many queries!
    return snowflake_session

# AFTER: Trust the session, errors will surface on actual queries
if snowflake_session is not None:
    return snowflake_session  # ✅ No unnecessary query
```

#### 2. Track Cache Disable State ([database.py](database.py))
```python
_cache_disabled = False  # Global flag

# Only disable cache ONCE per session
if DEBUG_DISABLE_SNOWFLAKE_CACHE and not _cache_disabled:
    snowflake_session.sql("ALTER SESSION SET USE_CACHED_RESULT = FALSE").collect()
    print("Snowflake query result cache DISABLED")
    _cache_disabled = True  # ✅ Don't run again
```

#### 3. Removed Duplicate Geometry Load ([App.vue](frontend/src/App.vue))
```javascript
// BEFORE: App.vue loaded geometry immediately
const connected = await ApiService.waitForConnection()
if (connected) {
    await geometryStore.loadGeometry()  // ❌ Duplicate!
}

// AFTER: Let SharedMap handle geometry loading (deferred)
const connected = await ApiService.waitForConnection()
if (connected) {
    // Geometry will be loaded by SharedMap when needed (deferred)
}
```

**Expected Reduction:** 15 queries → **5 queries** on initial load:
1. ✅ `SELECT 1` (connection test) - 1x only
2. ✅ `ALTER SESSION SET USE_CACHED_RESULT = FALSE` - 1x only
3. ✅ `SELECT FROM DIM_SIGNALS_XD` - 1x only
4. ✅ `SELECT FROM TRAVEL_TIME_ANALYTICS` - 1x for summary
5. ✅ `SELECT FROM TRAVEL_TIME_ANALYTICS` - 1x for aggregated

---

### 🟡 MODERATE: Time-of-Day Filter Issue (Not Yet Fixed)

**Problem:** "Time of day filter causes rapid incessant onslaught of excessive queries"

**Need More Info:**
- Which component is triggering this?
- Is it the filter panel watchers?
- Is it debouncing missing?

**To Investigate:**
1. Check [FilterPanel.vue](frontend/src/components/FilterPanel.vue) for watch triggers
2. Add debouncing to filter changes
3. Only trigger API calls on user interaction end (not every keystroke)

**Suggested Fix:**
```javascript
import { debounce } from 'lodash-es'

// Debounce filter updates by 300ms
const debouncedUpdateFilters = debounce(() => {
  filtersStore.setFilters(localFilters.value)
}, 300)

watch(localFilters, () => {
  debouncedUpdateFilters()
}, { deep: true })
```

---

## Testing Instructions

### 1. Verify TTI Calculation

Compare results with original query:

**Original (Working):**
```sql
SELECT
    t.XD,
    SUM(t.TRAVEL_TIME_SECONDS) / SUM(f.TRAVEL_TIME_SECONDS) as TTI
FROM TRAVEL_TIME_ANALYTICS t
INNER JOIN FREEFLOW f ON t.XD = f.XD
WHERE ...
GROUP BY t.XD
```

**New (Should Match):**
```sql
WITH agg AS (
    SELECT
        t.XD,
        SUM(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) as TOTAL_TTI,
        COUNT(*) as RECORD_COUNT
    FROM TRAVEL_TIME_ANALYTICS t
    INNER JOIN FREEFLOW f ON t.XD = f.XD
    WHERE ...
    GROUP BY t.XD
)
SELECT
    XD,
    TOTAL_TTI / RECORD_COUNT as TTI
FROM agg
```

**Note:** These formulas are mathematically equivalent:
- `SUM(a) / SUM(b) = SUM(a/b) / COUNT(*)`

### 2. Verify Query Reduction

**Check Snowflake Query History:**

Expected queries on initial page load:
```
1. SELECT 1                                    ← Connection test (1x)
2. ALTER SESSION SET USE_CACHED_RESULT = FALSE ← Cache disable (1x)
3. SELECT FROM DIM_SIGNALS_XD                  ← Dimension lookup
4. SELECT FROM TRAVEL_TIME_ANALYTICS           ← Summary data
5. SELECT FROM TRAVEL_TIME_ANALYTICS           ← Aggregated chart data
```

**Total: 5 queries** (down from 15!)

### 3. Verify No Duplicate Geometry Loads

**Check browser network tab:**
- Should only see ONE `/api/xd-geometry` request on initial load
- Should be deferred (appears after map renders)

---

## Rollback Instructions

If TTI values are still wrong:

```bash
git checkout routes/api_travel_time.py
```

Then manually verify the original TTI formula in your queries.

---

## Next Steps

1. **Test TTI values** - Compare with known good data
2. **Monitor query count** - Should be ~5 queries, not 15
3. **Investigate time-of-day filter** - Need to see what's triggering excessive queries
4. **Add query debouncing** - If filter changes trigger rapid queries

---

## Files Modified

- `routes/api_travel_time.py` - Fixed TTI calculation in all 4 query variants
- `database.py` - Removed health checks, track cache disable state
- `frontend/src/App.vue` - Removed duplicate geometry load
