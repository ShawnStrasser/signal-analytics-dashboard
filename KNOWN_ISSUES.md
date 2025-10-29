# Known Issues

## Many-to-Many Relationship Handling in DIM_SIGNALS_XD

### Issue Description
The `DIM_SIGNALS_XD` table has a many-to-many relationship between signals and XD segments:
- One XD segment can be mapped to multiple signals (same XD, different signal IDs)
- One signal can be mapped to multiple XD segments

This creates several issues in the current implementation that need to be addressed in the future.

### Affected Areas

#### 1. `create_xd_lookup_dict()` in utils/query_utils.py (Line 118-135)
**Problem**: This function creates a `XD -> signal info` mapping using a simple dictionary. When multiple signals map to the same XD, the function overwrites previous entries, keeping only the last signal's information.

**Impact**: Data loss - only one arbitrary signal's metadata is retained per XD segment.

**Potential Fix**: Change return type to `Dict[int, List[Dict]]` to store all signals per XD, or create specialized functions for different use cases.

#### 2. `/travel-time-summary` endpoint in routes/api_travel_time.py (Line 247-260)
**Problem**: After joining analytics data with dimension data, the endpoint returns one row per dimension table row. Since dimension table has duplicate XDs (with different signal IDs), this creates duplicate XD entries in the map data.

**Impact**: Map may show duplicate markers for the same XD segment with different signal IDs.

**Potential Fix**: Group by XD and select one representative signal per XD, or explicitly handle the one-to-many relationship in the frontend by filtering duplicates.

#### 3. `/anomaly-summary` endpoint in routes/api_anomalies.py (Line 124-137)
**Problem**: Same issue as `/travel-time-summary` - returns duplicate XD entries when multiple signals map to the same XD.

**Impact**: Map may show duplicate anomaly markers for the same XD segment.

**Potential Fix**: Apply same solution as travel-time-summary endpoint.

### Workarounds Currently in Use
The legend feature implementation uses `SELECT DISTINCT` in subqueries to handle the many-to-many relationship when grouping by legend fields. This approach picks one arbitrary value per unique legend field but avoids duplication in the chart data.

### Recommended Future Action
1. Decide on canonical approach for handling XD duplicates in map visualizations
2. Either deduplicate at query level (GROUP BY XD, pick one signal) or frontend level (filter out duplicate XDs)
3. Update `create_xd_lookup_dict()` to properly handle multiple signals per XD
4. Add database constraints or application logic to prevent unexpected duplications
5. Document the expected cardinality of the relationship in schema documentation

### Priority
Medium - Current workarounds prevent critical failures, but may cause confusion in map visualizations and data integrity concerns.


# OTHER ISSUES
### Some XD segments show 0 for TTI


