# Running the Tests (For AI Agent)

To run the Vitest unit tests that validate these issues:

```bash
# Navigate to frontend directory and run tests
cd "S:/Data_Analysis/Python/signal-analytics-dashboard/frontend" && npm test
```

**Test Files:**
- `frontend/src/stores/__tests__/selection.test.js` - Tests for the selection store logic
- `frontend/src/components/__tests__/SharedMap.test.js` - Tests for the SharedMap component

**Current Test Results (Before Fixes):**
- Total: 49 tests
- Passing: 45 tests
- Failing: 4 tests (2 for Issue #1, 2 for Issue #4)

**Important:** The 4 failing tests correctly identify the bugs described below. After implementing fixes, run the tests again to verify all 49 tests pass. The tests use Vitest with jsdom environment and mock Leaflet to avoid actual map rendering.

---

# Expected Map Interaction Behavior:
This is to describe the expected map interaction behavior for context in understanding the issues.

When the user clicks on a signal then the chart is filtered to that signal (or more accurately, the chart is filtered to the XD segments that have a relationship with that signal) and the selected signal style updates to have a thick black outline around it (or white when in dark mode), all the XD segments associated with that signal also have a that same outline, and a button appears to "Clear Map Selections". The user can click on other signals to add them to the selection. The user may similarly click on the XD segments to add or remove them from the selection. When the user deselects a signal, then all the XD semgents that are associated ONLY with that signal (and not with another that is currently selected) will be deselected. The user may also select/deselect XD segments independently, without having one of the associated signals selected. Any time any of these selections are done, the chart should update with new data. The map selections do not change teh underlying data for the map, only for the chart. 

# Issue 1: Chart not updating when XD segment is deselected
I clicked on a signal and the chart updated as expected and the xd segments are highlighted as expected. Then i clicked on one fo the highlghted xd segments to deselect it. The segment was deselected but the chart did not update. I checked the API request to find that the fronend is still requesting the data for the original signal selection, not the updated XD selection, including the now deselected XD segment.

# Issue 2: Filters Not Updating Map Data
When i change the time filter of the day of week filter, the chart data gets updated but the map data does not get updated. No request is made to the server for updated data either. If i change the date filter then the map data gets updated.  



# Issue 3: Duplicate Requests Sent to Server
Another problem (or question) i'm seeing is that when I change the date range filter, i see two duplicate requests! The network tab confirms these duplicate requests being sent to the server, see below:

127.0.0.1 - - [08/Oct/2025 11:46:48] "GET /api/travel-time-aggregated?start_date=2025-10-07&end_date=2025-10-08&valid_geometry=all&anomaly_type=All&start_hour=15&start_minute=45&end_hour=19&end_minute=0&day_of_week=2&xd_segments=769658493&xd_segments=429017357&xd_segments=429017358&xd_segments=1236959535&xd_segments=1237039363&xd_segments=1626498857 HTTP/1.1" 200 -
127.0.0.1 - - [08/Oct/2025 11:46:50] "GET /api/travel-time-summary?start_date=2025-10-07&end_date=2025-10-08&valid_geometry=all&anomaly_type=All&start_hour=15&start_minute=45&end_hour=19&end_minute=0&day_of_week=2 HTTP/1.1" 200 -
127.0.0.1 - - [08/Oct/2025 11:46:50] "GET /api/travel-time-aggregated?start_date=2025-10-07&end_date=2025-10-08&valid_geometry=all&anomaly_type=All&start_hour=15&start_minute=45&end_hour=19&end_minute=0&day_of_week=2&xd_segments=769658493&xd_segments=429017357&xd_segments=429017358&xd_segments=1236959535&xd_segments=1237039363&xd_segments=1626498857 HTTP/1.1" 200 -


# Issue 4: Shared XD Segments Incorrectly Deselected
When two signals share the same XD segment, and both signals are selected, deselecting one signal incorrectly removes the shared XD segment even though the other signal is still selected. For example: Signal 1 has XD segments [100, 200] and Signal 2 has XD segments [200, 300]. XD 200 is shared between both signals. When I select both signals, then deselect Signal 1, XD segment 200 gets deselected even though Signal 2 is still selected. XD 200 should remain selected because Signal 2 is still selected.