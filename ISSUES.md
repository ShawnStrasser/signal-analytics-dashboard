# Running the Tests (For AI Agent)

To run the Vitest unit tests that validate these issues:

```bash
# Navigate to frontend directory and run tests
cd "S:/Data_Analysis/Python/signal-analytics-dashboard/frontend" && npm test
```

**Test Files:**
- `frontend/src/stores/__tests__/selection.test.js` - Tests for the selection store logic
- `frontend/src/components/__tests__/SharedMap.test.js` - Tests for the SharedMap component

**Test Results:**
- Total: 49 tests
- ✅ All passing

**Status:** All issues below have been fixed and verified with tests.

---

# Expected Map Interaction Behavior:
This is to describe the expected map interaction behavior for context in understanding the issues.

When the user clicks on a signal then the chart is filtered to that signal (or more accurately, the chart is filtered to the XD segments that have a relationship with that signal) and the selected signal style updates to have a thick black outline around it (or white when in dark mode), all the XD segments associated with that signal also have a that same outline, and a button appears to "Clear Map Selections". The user can click on other signals to add them to the selection. The user may similarly click on the XD segments to add or remove them from the selection. When the user deselects a signal, then all the XD semgents that are associated ONLY with that signal (and not with another that is currently selected) will be deselected. The user may also select/deselect XD segments independently, without having one of the associated signals selected. Any time any of these selections are done, the chart should update with new data. The map selections do not change teh underlying data for the map, only for the chart. 

# Issue 1: Chart not updating when XD segment is deselected ✅ FIXED
**Problem:** I clicked on a signal and the chart updated as expected and the xd segments are highlighted as expected. Then i clicked on one fo the highlghted xd segments to deselect it. The segment was deselected but the chart did not update. I checked the API request to find that the fronend is still requesting the data for the original signal selection, not the updated XD selection, including the now deselected XD segment.

**Solution:** Updated `allSelectedXdSegments` computed property in `frontend/src/stores/selection.js` to return only the XD segments in `selectedXdSegments` set, ensuring manually deselected segments are properly removed from chart filters.

# Issue 2: Filters Not Updating Map Data ✅ FIXED
**Problem:** When i change the time filter of the day of week filter, the chart data gets updated but the map data does not get updated. No request is made to the server for updated data either. If i change the date filter then the map data gets updated.

**Solution:** Updated cache keys in `frontend/src/stores/mapDataCache.js` to include `startHour`, `startMinute`, `endHour`, `endMinute`, and `dayOfWeek`. Updated all cache getter/setter calls in `TravelTime.vue` and `Anomalies.vue` to pass these parameters, ensuring map data is correctly invalidated when time-of-day or day-of-week filters change.  



# Issue 3: Duplicate Requests Sent to Server ✅ FIXED
**Problem:** Another problem (or question) i'm seeing is that when I change the date range filter, i see two duplicate requests! The network tab confirms these duplicate requests being sent to the server, see below:

```
127.0.0.1 - - [08/Oct/2025 11:46:48] "GET /api/travel-time-aggregated?..." 200 -
127.0.0.1 - - [08/Oct/2025 11:46:50] "GET /api/travel-time-summary?..." 200 -
127.0.0.1 - - [08/Oct/2025 11:46:50] "GET /api/travel-time-aggregated?..." 200 - (DUPLICATE)
```

**Solution:** Added `startMinute`, `endMinute`, and `dayOfWeek` to the date/time filter watchers in `TravelTime.vue` and `Anomalies.vue`. This ensures all time-related filter changes are captured in a single watcher trigger, preventing multiple separate watcher invocations that caused duplicate requests.


# Issue 4: Shared XD Segments Incorrectly Deselected ✅ FIXED
**Problem:** When two signals share the same XD segment, and both signals are selected, deselecting one signal incorrectly removes the shared XD segment even though the other signal is still selected. For example: Signal 1 has XD segments [100, 200] and Signal 2 has XD segments [200, 300]. XD 200 is shared between both signals. When I select both signals, then deselect Signal 1, XD segment 200 gets deselected even though Signal 2 is still selected. XD 200 should remain selected because Signal 2 is still selected.

**Solution:** Updated `toggleSignal()` function in `frontend/src/stores/selection.js` to check if XD segments belong to other selected signals before removing them. When deselecting a signal, shared XD segments now remain selected if they're part of another currently selected signal.