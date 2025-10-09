# Database/Backend Updates
- Remove lat/long from dim_signals_xd (DONE!)
- Add DIM_SIGNALS (will have lat/long in it) (DONE!)
- Update backend to accept DIM_SIGNALS now and DIM_SIGNALS_XD in its updated form. see README.md for updated table definitions.

# Frontend Updates
Update the frontend (filters, maps and charts etc) to handle the above database changes too.

Update the map tooltips to have:
Signals: Replace ID with Name, Travel Time Index, remove Approach.
XDs: XD Segment, Bearing, Road, Miles, Approach, Travel Time Index

### Filters
Change the "Select Signals" filter to make it a heiarical filter with the DIM_SIGNALS District column as expandable groups, and have Name be under that. The filter needs to be searchable. It should have check boxes that allow selecting everything in a group.

Above the signals filter, add a new "Maintained By" filter which will have a dropdown option to single select between All, ODOT, Others. This filter acts on the select signals filter, so for example, if ODOT is selected then only ODOT maintained signals are shown in the map or in the select signals filter, and the chart would be filtered only to those XD segments that have relationsihps with ODOT maintained signals. 

Approach and Valid Geometry filters are making an api call but nothing is actually being change/updated as a result. These filters should be filtering the XD segments on the map and the underlying data. In DIM_SIGNALS_XD the same XD can be listed twice an Approach=True for one ID (signal) and Approach=False for another signal. In the case where there are multiple occurances of an XD, then take the MAX of the valid/approach column so that if any of them are true then they are shown on the map and labled as true. If none of the occurances of an XD are True and the filter is applied then it should get removed from the map, and the backend/database should handle the filtering with a join (see API calls section below). 


### API Calls
Efficiency improvments will be needed for API calls when selections on the signals filter or maintained by filter are made. For example if the user were to select "ODOT" in the maintained by filter, the API call cannot include a list of every XD segment for those signals, that list would be thousands long and make the request itself become large and inneficient. Instead, a more efficient way to construct teh queries is needed. A better way is to dynamically create join conditions based on the current filter selections and have the database use joins with the DIM_SIGNALS and DIM_SIGNALS_XD tables to filter to the correct XD segments in TRAVEL_TIME_ANALYTICS. 

API calls from the map interactions however should remain the same, they should still have direct calls that use the list of XD segments, since those ones will typically be a lot smaller. I'm only worried about how the calls resulting from filter interactions are handled. 
