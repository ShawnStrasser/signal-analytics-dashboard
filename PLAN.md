# Implementation Plan

This document outlines the changes needed to implement hierarchical signal filtering with district grouping and improved API efficiency.

## Implementation Steps (Recommended Order)

Implement these steps **one at a time** to ensure each piece works before moving on:

### Step 1: Add Maintained By Filter (Frontend Store Only) ✅ COMPLETED
**Goal:** Add maintainedBy state to filters store
**Files:** `frontend/src/stores/filters.js`
**Tests to pass:** 5 tests in "Maintained By Filter"
**Why first:** Simple, self-contained, no UI changes needed yet
**Dependencies:** None
**Status:** All 5 tests passing, watchers added to TravelTime.vue and Anomalies.vue

### Step 2: Backend API Efficiency Improvements ✅ COMPLETED (NEEDS REVISION)
**Goal:** Add join-based filtering support to backend APIs
**Files:** `routes/api_travel_time.py`, `routes/api_anomalies.py`, `utils/query_utils.py`
**Tests to pass:** 1 test in "API Efficiency"
**Why second:** Can be done independently, maintains backward compatibility
**Dependencies:** None (but benefits from Step 1)
**Status:** Partially complete - accepts parameters but NEEDS FIXING per Step 4a below

### Step 3: Hierarchical District Selection (Frontend Store) ✅ COMPLETED
**Goal:** Add district-level selection state and logic
**Files:** `frontend/src/stores/filters.js`
**Tests to pass:** 4 tests in "Hierarchical District Selection"
**Why third:** Builds on Step 1, more complex store logic
**Dependencies:** Step 1 (uses maintainedBy filter)
**Status:** Store functions complete

### Step 4: Update FilterPanel UI Components ✅ COMPLETED
**Goal:** Add UI controls for new filters
**Files:** `frontend/src/components/FilterPanel.vue`, `frontend/src/views/TravelTime.vue`, `frontend/src/views/Anomalies.vue`
**Tests:** Manual testing (UI/visual)
**Why fourth:** Requires Steps 1 & 3 to be complete
**Dependencies:** Steps 1 & 3
**Status:** Maintained By filter dropdown added, Filter Summary updated, watchers added to views

### Step 4a: Fix Backend Query Inefficiency ✅ COMPLETED (Travel Time endpoints only)
**Goal:** Eliminate XD collection and resubmission - do ALL filtering at database level
**Status:** Travel time endpoints updated (backend + frontend caching fixed), anomaly endpoints TODO
**Problem:** Current implementation:
1. Queries DIM_SIGNALS/DIM_SIGNALS_XD to get XD list (e.g., 5000 XDs)
2. Collects XDs in Python: `xd_list = [row['XD'] for row in filtered_xds.collect()]`
3. Sends XD list BACK to database: `WHERE XD IN (xd_list)`
**Solution:** Use JOINs to filter everything in a single SQL query

**Files:**
- `utils/query_utils.py` - Rewrite `build_xd_filter_with_joins()` to return SQL join clauses, not XD lists
- `routes/api_travel_time.py` - All endpoints (`/travel-time-summary`, `/travel-time-aggregated`, `/travel-time-by-time-of-day`)
- `routes/api_anomalies.py` - All endpoints (`/anomaly-summary`, `/anomaly-aggregated`)

**Target Query Pattern:**
```sql
-- Do NOT do this (current inefficient approach):
-- Step 1: SELECT XD FROM DIM_SIGNALS_XD JOIN DIM_SIGNALS ... (collect 5000 XDs)
-- Step 2: SELECT * FROM TRAVEL_TIME_ANALYTICS WHERE XD IN (xd_list)

-- Instead, do this (efficient single query):
SELECT
    t.TIMESTAMP,
    AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) AS TRAVEL_TIME_INDEX
FROM TRAVEL_TIME_ANALYTICS t
JOIN FREEFLOW f ON t.XD = f.XD
JOIN DIM_SIGNALS_XD xd ON t.XD = xd.XD
JOIN DIM_SIGNALS s ON xd.ID = s.ID
WHERE s.ODOT_MAINTAINED = FALSE
  AND t.DATE_ONLY BETWEEN '2025-10-07' AND '2025-10-09'
  AND xd.APPROACH = TRUE  -- if approach filter specified
  AND xd.VALID_GEOMETRY = TRUE  -- if valid_geometry filter specified
GROUP BY t.TIMESTAMP
ORDER BY t.TIMESTAMP;
```

**Implementation Details:**
- **For `/travel-time-summary`** (map data):
  ```sql
  SELECT
      s.ID,
      s.LATITUDE,
      s.LONGITUDE,
      s.DISTRICT,
      s.NAME,
      xd.XD,
      xd.APPROACH,
      xd.VALID_GEOMETRY,
      AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) AS TRAVEL_TIME_INDEX
  FROM DIM_SIGNALS s
  JOIN DIM_SIGNALS_XD xd ON s.ID = xd.ID
  LEFT JOIN TRAVEL_TIME_ANALYTICS t ON xd.XD = t.XD AND t.DATE_ONLY BETWEEN '2025-10-07' AND '2025-10-09'
  LEFT JOIN FREEFLOW f ON xd.XD = f.XD
  WHERE 1=1
    -- maintainedBy filter
    AND (s.ODOT_MAINTAINED = FALSE)  -- when maintainedBy='others'
    -- approach filter
    AND (xd.APPROACH = TRUE)  -- when approach=true
    -- valid_geometry filter
    AND (xd.VALID_GEOMETRY = TRUE)  -- when valid_geometry='valid'
  GROUP BY s.ID, s.LATITUDE, s.LONGITUDE, s.DISTRICT, s.NAME, xd.XD, xd.APPROACH, xd.VALID_GEOMETRY
  ```

- **For `/travel-time-aggregated`** and `/travel-time-by-time-of-day`** (chart data):
  ```sql
  SELECT
      t.TIMESTAMP,
      AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) AS TRAVEL_TIME_INDEX
  FROM TRAVEL_TIME_ANALYTICS t
  JOIN FREEFLOW f ON t.XD = f.XD
  JOIN DIM_SIGNALS_XD xd ON t.XD = xd.XD
  JOIN DIM_SIGNALS s ON xd.ID = s.ID
  WHERE t.DATE_ONLY BETWEEN '2025-10-07' AND '2025-10-09'
    AND (s.ODOT_MAINTAINED = FALSE)  -- maintainedBy filter
    AND (xd.APPROACH = TRUE)  -- approach filter
    AND (xd.VALID_GEOMETRY = TRUE)  -- valid_geometry filter
  GROUP BY t.TIMESTAMP
  ORDER BY t.TIMESTAMP
  ```

**Key Changes:**
1. **Remove `collect()` calls** - No more fetching XD lists into Python
2. **Add JOINs to main query** - Join DIM_SIGNALS_XD and DIM_SIGNALS directly in the analytics query
3. **Apply filters in WHERE clause** - All filtering happens in SQL
4. **Keep xd_segments parameter** - For map interactions (small XD lists are fine)

**Testing:**
- Verify maintainedBy filter works on both map and chart
- Check console for single SQL query (not two separate queries)
- Ensure performance improves for large signal selections

### Step 4b: Fetch and Cache DIM_SIGNALS Data ⏳ NOT STARTED
**Goal:** Fetch complete signal dimension data once and cache in frontend
**Why:** Need DISTRICT and ODOT_MAINTAINED columns for hierarchical filtering and maintainedBy client-side filtering

**Files:**
- Add new endpoint: `routes/api_travel_time.py` - `/api/dim-signals`
- Add new store: `frontend/src/stores/signals.js` - Cache DIM_SIGNALS data
- Update: `frontend/src/components/FilterPanel.vue` - Use cached signal data

**Backend Implementation:**
```python
@travel_time_bp.route('/dim-signals')
def get_dim_signals():
    """Get DIM_SIGNALS dimension data (cached on client)"""
    query = """
    SELECT
        ID,
        DISTRICT,
        LATITUDE,
        LONGITUDE,
        ODOT_MAINTAINED,
        NAME
    FROM DIM_SIGNALS
    ORDER BY DISTRICT, ID
    """
    arrow_data = session.sql(query).to_arrow()
    arrow_bytes = snowflake_result_to_arrow(arrow_data)
    return create_arrow_response(arrow_bytes)
```

**Frontend Store:**
```javascript
// frontend/src/stores/signals.js
export const useSignalsStore = defineStore('signals', () => {
  const dimSignals = ref([])  // Complete list from DIM_SIGNALS
  const dimSignalsXd = ref([]) // Complete list from DIM_SIGNALS_XD

  async function loadDimSignals() {
    if (dimSignals.value.length > 0) return // Already loaded
    const arrowTable = await ApiService.getDimSignals()
    dimSignals.value = ApiService.arrowTableToObjects(arrowTable)
  }

  // Filter by maintainedBy (client-side)
  const filteredSignals = computed(() => {
    const filtersStore = useFiltersStore()
    let filtered = dimSignals.value

    if (filtersStore.maintainedBy === 'odot') {
      filtered = filtered.filter(s => s.ODOT_MAINTAINED === true)
    } else if (filtersStore.maintainedBy === 'others') {
      filtered = filtered.filter(s => s.ODOT_MAINTAINED === false)
    }

    return filtered
  })

  // Group by district (for hierarchical UI)
  const signalsByDistrict = computed(() => {
    const grouped = {}
    filteredSignals.value.forEach(signal => {
      const district = signal.DISTRICT || 'Unknown'
      if (!grouped[district]) grouped[district] = []
      grouped[district].push(signal)
    })
    return grouped
  })

  return { dimSignals, loadDimSignals, filteredSignals, signalsByDistrict }
})
```

### Step 4c: Filter Map Display by maintainedBy ⏳ NOT STARTED
**Goal:** Map should only show signals/XDs that match the maintainedBy filter
**Problem:** Currently maintainedBy filter updates chart but NOT the map

**Files:**
- `frontend/src/views/TravelTime.vue` - Filter mapData before passing to SharedMap
- `frontend/src/views/Anomalies.vue` - Same
- `frontend/src/components/SharedMap.vue` - May need updates if XD filtering needed

**Implementation:**
```javascript
// In TravelTime.vue
const displayedMapData = computed(() => {
  // Use cached signal data to filter map display
  const signalsStore = useSignalsStore()
  const allowedSignalIds = new Set(signalsStore.filteredSignals.map(s => s.ID))

  return mapData.value.filter(item => allowedSignalIds.has(item.ID))
})

// Pass displayedMapData to SharedMap instead of mapData
<SharedMap :signals="displayedMapData" ... />
```

**Options for XD segments:**
1. **Filter out completely** - Don't show XDs for filtered-out signals
2. **Grey out** - Show XDs but with reduced opacity (easier for user to understand)

**Decision:** Start with filtering out completely (simpler), can add greying later if needed.

### Step 5: Hierarchical District Filter UI ⏳ NOT STARTED
**Goal:** Replace flat signal dropdown with hierarchical district-grouped selector
**Dependencies:** Step 4b (needs DIM_SIGNALS data cached)

**Files:**
- `frontend/src/components/FilterPanel.vue`

**UI Design:**
```
┌─────────────────────────────────────┐
│ Maintained By: [All ▼]              │ ← Existing dropdown
├─────────────────────────────────────┤
│ Select Signals (by District):       │
│ ┌─────────────────────────────────┐ │
│ │ 🔍 Search...                     │ │
│ ├─────────────────────────────────┤ │
│ │ ☑ District 1 (15 signals)       │ │ ← District checkbox
│ │   ☑ Signal 101 - Main St        │ │
│ │   ☑ Signal 102 - Elm Ave        │ │
│ │   ☐ Signal 103 - Oak Blvd       │ │
│ │ ☐ District 2 (23 signals)       │ │
│ │   ☐ Signal 201 - Pine Rd        │ │
│ │   ☐ Signal 202 - Maple Dr       │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

**Implementation:**
- Use Vuetify `v-treeview` or custom grouped `v-autocomplete`
- Show signal NAME instead of just ID
- Allow district-level selection (selects all signals in district)
- Allow individual signal deselection within district
- Filtered by maintainedBy (districts with no matching signals hidden)

### Step 6: Fix Approach & Valid Geometry Filtering ⏳ NOT STARTED
**Goal:** Ensure approach/validGeometry filters work correctly with MAX aggregation
**Dependencies:** Step 4a (efficient join-based queries)

**Problem:** Same XD can appear multiple times in DIM_SIGNALS_XD with different APPROACH/VALID_GEOMETRY values
**Solution:** Use MAX() aggregation when filtering (if any occurrence is TRUE, treat as TRUE)

**Already handled in Step 4a queries** - Just verify behavior is correct.

### Step 7: Update Map Tooltips ⏳ NOT STARTED
**Goal:** Show correct fields in signal and XD tooltips
**Files:** `frontend/src/components/SharedMap.vue`
**Tests:** Manual testing (UI/visual)

**Signal Markers:**
- Current: `ID, Approach, Travel Time Index`
- New: `NAME, Travel Time Index` (remove Approach - signals don't have it)

**XD Segments:**
- Current: Minimal info
- New: `XD: <XD>, Bearing: <BEARING>, Road: <ROADNAME>, Miles: <MILES>, Approach: <APPROACH>, TTI: <index>`

---

## Current Status

**Completed:**
- ✅ Step 1: Maintained By filter state
- ✅ Step 2: Backend accepts parameters (but inefficient)
- ✅ Step 3: District selection store functions
- ✅ Step 4: Maintained By dropdown UI + watchers

**In Progress:**
- ⚠️ Step 4a: Fix backend query inefficiency (CURRENT TASK)

**Not Started:**
- ⏳ Step 4b: Fetch and cache DIM_SIGNALS
- ⏳ Step 4c: Filter map display
- ⏳ Step 5: Hierarchical district UI
- ⏳ Step 6: Verify approach/validGeometry
- ⏳ Step 7: Update tooltips

---

## Architecture Notes

### Data Flow for maintainedBy Filter:

1. **User changes "Maintained By" dropdown** (All → ODOT)
2. **Frontend:**
   - filtersStore.maintainedBy = 'odot'
   - Watchers in TravelTime.vue trigger data reload
   - signalsStore.filteredSignals updates (client-side filter)
3. **API Request:**
   - `/travel-time-summary?maintained_by=odot`
   - `/travel-time-aggregated?maintained_by=odot`
4. **Backend (Single Efficient Query):**
   ```sql
   SELECT t.*, AVG(...)
   FROM TRAVEL_TIME_ANALYTICS t
   JOIN FREEFLOW f ON t.XD = f.XD
   JOIN DIM_SIGNALS_XD xd ON t.XD = xd.XD
   JOIN DIM_SIGNALS s ON xd.ID = s.ID
   WHERE s.ODOT_MAINTAINED = TRUE
   ```
5. **Frontend Display:**
   - Map filters signals: `displayedMapData = mapData.filter(item => allowedSignalIds.has(item.ID))`
   - Chart shows filtered data
   - Signal selector shows only ODOT signals

### Key Design Decisions:

1. **Backend: ALL filtering in SQL** - No collecting XD lists in Python
2. **Frontend: Cache DIM_SIGNALS** - Fetch once, filter client-side for UI
3. **Map filtering: Hide filtered signals** - Don't show signals that don't match maintainedBy
4. **XD segments: Follow parent signal** - If signal is filtered out, its XDs are too

---

## Important Schema Notes

- `DIM_SIGNALS.ODOT_MAINTAINED` is **BOOLEAN** (not string)
- `DIM_SIGNALS_XD.ROADNAME` (not 'ROAD')
- `DIM_SIGNALS.ID` and `DIM_SIGNALS_XD.ID` are **VARCHAR** (not INT)
- `DIM_SIGNALS.DISTRICT` is **VARCHAR** (for hierarchical grouping)
- `DIM_SIGNALS.NAME` is **VARCHAR** (for display in UI)
- All Snowflake column names are **UPPERCASE**
