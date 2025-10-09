# Implementation Plan

This document outlines the changes needed to implement hierarchical signal filtering with district grouping and improved API efficiency.

## Test Coverage

Unit tests have been created to validate implementation. Tests are in:
- `frontend/src/stores/__tests__/filters.test.js` (38 tests)
- `frontend/src/test-utils/index.js` (updated with new mock data helpers)

**Current Test Status: 26 PASS / 12 FAIL**

Run tests with: `cd frontend && npm test`

### Tests Passing ✅
- Initial state (4/4)
- Approach and Valid Geometry filtering (4/4)
- Existing features (18/18): Date range, signal selection, time-of-day, day-of-week, aggregation level, anomaly type

### Tests Failing (Expected) ❌
These will pass once features are implemented:

1. **Maintained By Filter (5 tests)**:
   - `store.maintainedBy` state missing
   - `store.setMaintainedBy()` action missing
   - `filterParams.maintained_by` not included

2. **Hierarchical District Selection (4 tests)**:
   - `store.selectedDistricts` state missing
   - `store.selectDistrict()` action missing
   - `store.deselectDistrict()` action missing
   - `store.filteredSignalsByDistrict` computed property missing

3. **Edge Cases (2 tests)**:
   - Invalid date range handling (minor)
   - Individual signal deselection within district

4. **API Efficiency (1 test)**:
   - Filter-based params instead of XD lists

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
Current tooltip shows: `ID`, `Approach`, `Travel Time Index`
- [ ] Replace `ID` with `NAME` (from DIM_SIGNALS)
- [ ] Remove `Approach` field
- [ ] Keep `Travel Time Index`
- **New format:** `Name, Travel Time Index`

#### XD Segments
Current tooltip shows: minimal info
- [ ] Add `XD Segment` (the XD ID)
- [ ] Add `Bearing` (from DIM_SIGNALS_XD)
- [ ] Add `Road` (from DIM_SIGNALS_XD)
- [ ] Add `Miles` (from DIM_SIGNALS_XD)
- [ ] Add `Approach` (from DIM_SIGNALS_XD)
- [ ] Add `Travel Time Index`
- **New format:** `XD Segment, Bearing, Road, Miles, Approach, Travel Time Index`

**Tests:** Manual testing required (visual/UI)

### Filters

**Implementation Checklist:**

#### 1. Maintained By Filter
**File:** `frontend/src/stores/filters.js`
- [ ] Add state: `const maintainedBy = ref('all')`
- [ ] Add action: `function setMaintainedBy(value) { maintainedBy.value = value }`
- [ ] Update `filterParams` computed to include `maintained_by: maintainedBy.value !== 'all' ? maintainedBy.value : undefined`
- [ ] Export `maintainedBy` and `setMaintainedBy` in return statement

**Tests to pass:** 5 tests in "PLAN.md Feature: Maintained By Filter"

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

**New (Efficient):**
```python
# Frontend sends: signal_ids=[1,2,3], maintained_by='odot', approach=True, valid_geometry='valid'
# Backend uses joins:
WITH filtered_xds AS (
  SELECT xd.XD
  FROM DIM_SIGNALS_XD xd
  JOIN DIM_SIGNALS sig ON xd.ID = sig.ID
  WHERE sig.ID IN (1,2,3)  -- OR sig.MAINTAINED_BY = 'ODOT'
    AND xd.APPROACH = CASE WHEN ? IS NOT NULL THEN ? ELSE xd.APPROACH END
    AND (? = 'all' OR (? = 'valid' AND xd.VALID_GEOMETRY = TRUE) OR (? = 'invalid' AND xd.VALID_GEOMETRY = FALSE))
)
SELECT * FROM TRAVEL_TIME_ANALYTICS tta
WHERE tta.XD IN (SELECT XD FROM filtered_xds)
```

#### Implementation Steps

**File:** `routes/api_travel_time.py`
- [ ] Accept new params: `signal_ids`, `maintained_by`
- [ ] Build dynamic join query when `signal_ids` or `maintained_by` provided
- [ ] Use `MAX(APPROACH)` and `MAX(VALID_GEOMETRY)` for duplicate XDs
- [ ] Keep `xd_segments` param for map-based queries (small lists)
- [ ] Add logic to choose between join-based or direct XD filtering

**File:** `routes/api_anomalies.py`
- [ ] Same changes as above

**File:** `database.py` (optional helper)
- [ ] Add helper function: `build_xd_filter_query(signal_ids, maintained_by, approach, valid_geometry)`

#### Query Decision Logic
```python
if xd_segments:
    # Map interaction - use direct XD list (small)
    query = query.filter(XD.in_(xd_segments))
elif signal_ids or maintained_by:
    # Filter panel - use joins (efficient)
    query = build_join_filtered_query(signal_ids, maintained_by, approach, valid_geometry)
```

**Tests to pass:** 1 test in "PLAN.md Feature: API Efficiency with Filter-Based Queries"

---

**Important Notes:**
- API calls from **map interactions** should continue using `xd_segments` lists (typically small)
- API calls from **filter panel** should use `signal_ids` + `maintained_by` + joins (efficient for large selections)
- Backend must handle both query types 
