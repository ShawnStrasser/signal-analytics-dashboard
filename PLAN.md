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
**Status:** All 5 tests passing (32/38 total tests passing)

### Step 2: Backend API Efficiency Improvements ✅ COMPLETED
**Goal:** Add join-based filtering support to backend APIs
**Files:** `routes/api_travel_time.py`, `routes/api_anomalies.py`
**Tests to pass:** 1 test in "API Efficiency"
**Why second:** Can be done independently, maintains backward compatibility
**Dependencies:** None (but benefits from Step 1)

### Step 3: Hierarchical District Selection (Frontend Store) ✅ COMPLETED
**Goal:** Add district-level selection state and logic
**Files:** `frontend/src/stores/filters.js`
**Tests to pass:** 4 tests in "Hierarchical District Selection"
**Why third:** Builds on Step 1, more complex store logic
**Dependencies:** Step 1 (uses maintainedBy filter)

### Step 4: Update FilterPanel UI Components
**Goal:** Add UI controls for new filters
**Files:** `frontend/src/components/FilterPanel.vue`
**Tests:** Manual testing (UI/visual)
**Why fourth:** Requires Steps 1 & 3 to be complete
**Dependencies:** Steps 1 & 3

### Step 5: Fix Approach & Valid Geometry Filtering
**Goal:** Ensure approach/validGeometry filters actually work
**Files:** Backend query logic (uses Step 2 infrastructure)
**Tests:** Existing tests already pass, just need to verify behavior
**Why fifth:** Leverages join infrastructure from Step 2
**Dependencies:** Step 2

### Step 6: Update Map Tooltips
**Goal:** Show correct fields in signal and XD tooltips
**Files:** `frontend/src/components/SharedMap.vue`
**Tests:** Manual testing (UI/visual)
**Why last:** Independent, pure UI change, no breaking changes
**Dependencies:** None

---

**IMPORTANT:** All column names and schemas strictly follow `README.md`. Key points:
- `DIM_SIGNALS.ODOT_MAINTAINED` is a **BOOLEAN** (not a string like 'ODOT', 'City', etc.)
- `DIM_SIGNALS_XD.ROADNAME` (not 'ROAD')
- `DIM_SIGNALS.ID` and `DIM_SIGNALS_XD.ID` are **VARCHAR** (not INT)
- All Snowflake column names are **UPPERCASE**

## Test Coverage

Unit tests have been created to validate implementation. Tests are in:
- `frontend/src/stores/__tests__/filters.test.js` (38 tests)
- `frontend/src/test-utils/index.js` (updated with new mock data helpers)

**Current Test Status: 32 PASS / 6 FAIL**

Run tests with: `cd frontend && npm test`

### Tests Passing ✅
- Initial state (4/4)
- Approach and Valid Geometry filtering (4/4)
- Existing features (18/18): Date range, signal selection, time-of-day, day-of-week, aggregation level, anomaly type
- **Maintained By Filter (5/5)** ✅ STEP 1 COMPLETE
- API Efficiency (2/2)

### Tests Failing (Expected) ❌
These will pass once features are implemented:

1. **Hierarchical District Selection (4 tests)**:
   - `store.selectedDistricts` state missing
   - `store.selectDistrict()` action missing
   - `store.deselectDistrict()` action missing
   - `store.filteredSignalsByDistrict` computed property missing

2. **Edge Cases (2 tests)**:
   - Invalid date range handling (minor)
   - Individual signal deselection within district

---

# Database/Backend Updates
- Remove lat/long from dim_signals_xd (DONE!)
- Add DIM_SIGNALS (will have lat/long in it) (DONE!)
- Update backend to accept DIM_SIGNALS now and DIM_SIGNALS_XD in its updated form. see README.md for updated table definitions.

# Frontend Updates
Update the frontend (filters, maps and charts etc) to handle the above database changes too.

### Map Tooltips

**Implementation Checklist:**

**File:** `frontend/src/components/SharedMap.vue`

#### Signal Markers
**Data source:** `DIM_SIGNALS` table

Current tooltip shows: `ID`, `Approach`, `Travel Time Index`
- [ ] Replace `ID` with `NAME` (VARCHAR from DIM_SIGNALS)
- [ ] Remove `Approach` field (signals don't have approach, XD segments do)
- [ ] Keep `Travel Time Index`
- **New format:** `<NAME>, Travel Time Index`

#### XD Segments
**Data source:** `DIM_SIGNALS_XD` table

Current tooltip shows: minimal info
- [ ] Add `XD` (INT - the XD segment ID)
- [ ] Add `BEARING` (VARCHAR from DIM_SIGNALS_XD)
- [ ] Add `ROADNAME` (VARCHAR from DIM_SIGNALS_XD)
- [ ] Add `MILES` (DOUBLE from DIM_SIGNALS_XD)
- [ ] Add `APPROACH` (BOOLEAN from DIM_SIGNALS_XD)
- [ ] Add `Travel Time Index` (calculated/aggregated)
- **New format:** `XD: <XD>, Bearing: <BEARING>, Road: <ROADNAME>, Miles: <MILES>, Approach: <APPROACH>, TTI: <index>`

**Tests:** Manual testing required (visual/UI)

### Filters

**Implementation Checklist:**

#### 1. Maintained By Filter
**Database Column:** `DIM_SIGNALS.ODOT_MAINTAINED` (BOOLEAN)

**File:** `frontend/src/stores/filters.js`
- [x] Add state: `const maintainedBy = ref('all')`
  - Values: `'all'` (no filter), `'odot'` (ODOT_MAINTAINED = TRUE), `'others'` (ODOT_MAINTAINED = FALSE)
- [x] Add action: `function setMaintainedBy(value) { maintainedBy.value = value }`
- [x] Update `filterParams` computed to include `maintained_by: maintainedBy.value !== 'all' ? maintainedBy.value : undefined`
- [x] Export `maintainedBy` and `setMaintainedBy` in return statement

**Tests to pass:** 5 tests in "PLAN.md Feature: Maintained By Filter" ✅ ALL PASSING

#### 2. Hierarchical Signal Selection with Districts
**File:** `frontend/src/stores/filters.js`
- [ ] Add state: `const selectedDistricts = ref([])`
- [ ] Add action: `function selectDistrict(district, signalIds) { ... }`
- [ ] Add action: `function deselectDistrict(district, signalIds) { ... }`
- [ ] Add action: `function deselectIndividualSignal(signalId) { ... }`
- [ ] Add computed: `const filteredSignalsByDistrict = computed(() => { ... })`
  - Groups signals by DISTRICT
  - Filters by maintainedBy when not 'all'
- [ ] Export all new state, actions, and computed in return statement

**File:** `frontend/src/components/FilterPanel.vue`
- [ ] Replace signal select with hierarchical tree/grouped select
- [ ] Add "Maintained By" dropdown above signal filter
- [ ] Options: "All", "ODOT", "Others"
- [ ] Make signals searchable by name or district
- [ ] Add checkboxes for selecting entire districts

**Tests to pass:** 4 tests in "PLAN.md Feature: Hierarchical Signal Selection with Districts"

#### 3. Approach and Valid Geometry Filtering
**Status:** Filter state already working, but needs backend implementation

Approach and Valid Geometry filters are making an api call but nothing is actually being change/updated as a result. These filters should be filtering the XD segments on the map and the underlying data. In DIM_SIGNALS_XD the same XD can be listed twice an Approach=True for one ID (signal) and Approach=False for another signal. In the case where there are multiple occurances of an XD, then take the MAX of the valid/approach column so that if any of them are true then they are shown on the map and labled as true. If none of the occurances of an XD are True and the filter is applied then it should get removed from the map, and the backend/database should handle the filtering with a join (see API calls section below).

**Tests status:** Already passing (filters included in filterParams) 


### API Calls

**Implementation Checklist:**

#### Backend Changes Required

**Files to modify:**
- `routes/api_travel_time.py`
- `routes/api_anomalies.py`

#### Query Strategy

**Current (Inefficient):**
```python
# Frontend sends: xd_segments=[100, 200, 300, ..., 9999]  # Thousands of XDs
# Backend filters: WHERE XD IN (100, 200, 300, ..., 9999)
```

**New (Efficient) - Using Correct Schema:**
```sql
-- Schema Reference:
-- DIM_SIGNALS: ID (VARCHAR), DISTRICT (VARCHAR), LATITUDE (DOUBLE), LONGITUDE (DOUBLE),
--              ODOT_MAINTAINED (BOOLEAN), NAME (VARCHAR)
-- DIM_SIGNALS_XD: ID (VARCHAR), VALID_GEOMETRY (BOOLEAN), XD (INT), BEARING (VARCHAR),
--                 COUNTY (VARCHAR), ROADNAME (VARCHAR), MILES (DOUBLE),
--                 APPROACH (BOOLEAN), EXTENDED (BOOLEAN)

-- Frontend sends: signal_ids=['1','2','3'], maintained_by='odot', approach=true, valid_geometry='valid'

-- Backend builds query with joins:
WITH FILTERED_XDS AS (
  SELECT
    XD_TABLE.XD,
    MAX(XD_TABLE.APPROACH) AS APPROACH,           -- Take MAX for duplicate XDs
    MAX(XD_TABLE.VALID_GEOMETRY) AS VALID_GEOMETRY -- Take MAX for duplicate XDs
  FROM DIM_SIGNALS_XD AS XD_TABLE
  JOIN DIM_SIGNALS AS SIG_TABLE ON XD_TABLE.ID = SIG_TABLE.ID
  WHERE
    -- Filter by signal IDs (if provided)
    (SIG_TABLE.ID IN ('1', '2', '3'))
    -- Filter by ODOT_MAINTAINED (if not 'all')
    AND (
      :maintained_by = 'all'
      OR (:maintained_by = 'odot' AND SIG_TABLE.ODOT_MAINTAINED = TRUE)
      OR (:maintained_by = 'others' AND SIG_TABLE.ODOT_MAINTAINED = FALSE)
    )
    -- Filter by approach (if specified)
    AND (:approach IS NULL OR XD_TABLE.APPROACH = :approach)
    -- Filter by valid_geometry (if not 'all')
    AND (
      :valid_geometry = 'all'
      OR (:valid_geometry = 'valid' AND XD_TABLE.VALID_GEOMETRY = TRUE)
      OR (:valid_geometry = 'invalid' AND XD_TABLE.VALID_GEOMETRY = FALSE)
    )
  GROUP BY XD_TABLE.XD  -- Group to handle duplicate XDs with MAX aggregation
)
SELECT TTA.*
FROM TRAVEL_TIME_ANALYTICS AS TTA
WHERE TTA.XD IN (SELECT XD FROM FILTERED_XDS)
```

#### Implementation Steps

**File:** `routes/api_travel_time.py`
- [ ] Accept new params from frontend:
  - `signal_ids` (List[str]) - List of signal IDs (DIM_SIGNALS.ID)
  - `maintained_by` (str) - One of: 'all', 'odot', 'others'
- [ ] Build dynamic join query when `signal_ids` or `maintained_by != 'all'`
- [ ] Use `MAX(APPROACH)` and `MAX(VALID_GEOMETRY)` with GROUP BY XD to handle duplicate XDs
- [ ] Keep `xd_segments` param for map-based queries (small lists, direct XD filtering)
- [ ] Add logic to choose between join-based or direct XD filtering

**File:** `routes/api_anomalies.py`
- [ ] Same changes as above

**File:** `database.py` (optional helper)
- [ ] Add helper function: `build_xd_filter_query(session, signal_ids, maintained_by, approach, valid_geometry)`
- [ ] Returns CTE or subquery for filtered XD list

#### Query Decision Logic (Python/Snowpark)
```python
from snowflake.snowpark.functions import col, max as max_

# Get params from request
xd_segments = request.args.get('xd_segments')  # List[int] from map clicks
signal_ids = request.args.get('signal_ids')     # List[str] from filter panel
maintained_by = request.args.get('maintained_by', 'all')
approach = request.args.get('approach')         # True/False/None
valid_geometry = request.args.get('valid_geometry', 'all')

if xd_segments:
    # Map interaction - use direct XD list (small, efficient)
    xd_list = [int(xd) for xd in xd_segments.split(',')]
    tta_data = session.table('TRAVEL_TIME_ANALYTICS').filter(col('XD').isin(xd_list))

elif signal_ids or maintained_by != 'all':
    # Filter panel - use joins (efficient for large selections)

    # Build filtered XD CTE
    xd_table = session.table('DIM_SIGNALS_XD').alias('XD_TABLE')
    sig_table = session.table('DIM_SIGNALS').alias('SIG_TABLE')

    # Join tables
    joined = xd_table.join(sig_table, xd_table['ID'] == sig_table['ID'])

    # Apply filters
    if signal_ids:
        signal_id_list = signal_ids.split(',')
        joined = joined.filter(col('SIG_TABLE.ID').isin(signal_id_list))

    if maintained_by == 'odot':
        joined = joined.filter(col('SIG_TABLE.ODOT_MAINTAINED') == True)
    elif maintained_by == 'others':
        joined = joined.filter(col('SIG_TABLE.ODOT_MAINTAINED') == False)

    if approach is not None:
        joined = joined.filter(col('XD_TABLE.APPROACH') == approach)

    if valid_geometry == 'valid':
        joined = joined.filter(col('XD_TABLE.VALID_GEOMETRY') == True)
    elif valid_geometry == 'invalid':
        joined = joined.filter(col('XD_TABLE.VALID_GEOMETRY') == False)

    # Aggregate with MAX to handle duplicate XDs
    filtered_xds = joined.group_by('XD_TABLE.XD').agg(
        max_(col('XD_TABLE.APPROACH')).alias('APPROACH'),
        max_(col('XD_TABLE.VALID_GEOMETRY')).alias('VALID_GEOMETRY')
    ).select('XD')

    # Get XD list
    xd_list = [row['XD'] for row in filtered_xds.collect()]

    # Filter TRAVEL_TIME_ANALYTICS
    tta_data = session.table('TRAVEL_TIME_ANALYTICS').filter(col('XD').isin(xd_list))
```

**Tests to pass:** 1 test in "PLAN.md Feature: API Efficiency with Filter-Based Queries"

---

**Important Notes:**
- API calls from **map interactions** should continue using `xd_segments` lists (typically small)
- API calls from **filter panel** should use `signal_ids` + `maintained_by` + joins (efficient for large selections)
- Backend must handle both query types 
