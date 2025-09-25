"""
Travel Time Analysis Page
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.database import get_travel_time_data, get_travel_time_summary, get_travel_time_aggregated
from utils.performance import time_function, time_block, log_performance


# Add caching to reduce redundant database calls
@st.cache_data(ttl=300)  # Cache for 5 minutes
def cached_get_travel_time_summary(session_id, start_date, end_date, signal_ids, approach, valid_geometry):
    """Cached version of get_travel_time_summary to reduce database calls during page switches."""
    from utils.database import get_snowflake_session
    session = get_snowflake_session()
    return get_travel_time_summary(session, start_date, end_date, signal_ids, approach, valid_geometry)


@st.cache_data(ttl=300)  # Cache for 5 minutes  
def cached_get_travel_time_aggregated(session_id, start_date, end_date, signal_ids, approach, valid_geometry):
    """Cached version of get_travel_time_aggregated to reduce database calls during page switches."""
    from utils.database import get_snowflake_session
    session = get_snowflake_session()
    return get_travel_time_aggregated(session, start_date, end_date, signal_ids, approach, valid_geometry)


@time_function("create_travel_time_map_plotly")
def create_travel_time_map_plotly(summary_df):
    """Create a Plotly scatter mapbox with travel time visualizations - much faster than Folium."""
    
    if summary_df.empty:
        return None
    
    with time_block("Prepare data for Plotly map"):
        # Add color and size columns for Plotly
        df_map = summary_df.copy()
        
        # Normalize bubble sizes (10-50 pixel range)
        max_travel_time = df_map['TOTAL_TRAVEL_TIME'].max()
        min_travel_time = df_map['TOTAL_TRAVEL_TIME'].min()
        
        if max_travel_time > min_travel_time:
            df_map['marker_size'] = 10 + (df_map['TOTAL_TRAVEL_TIME'] - min_travel_time) / (max_travel_time - min_travel_time) * 40
        else:
            df_map['marker_size'] = 25
            
        # Color based on average travel time
        df_map['color_category'] = pd.cut(
            df_map['AVG_TRAVEL_TIME'], 
            bins=[0, 30, 60, 120, float('inf')], 
            labels=['Good (<30s)', 'Fair (30-60s)', 'Poor (60-120s)', 'Critical (>120s)'],
            include_lowest=True
        )
        
        # Create hover text
        df_map['hover_text'] = (
            "<b>Signal ID:</b> " + df_map['ID'].astype(str) + "<br>" +
            "<b>Total Travel Time:</b> " + df_map['TOTAL_TRAVEL_TIME'].round(0).astype(str) + " seconds<br>" +
            "<b>Average Travel Time:</b> " + df_map['AVG_TRAVEL_TIME'].round(1).astype(str) + " seconds<br>" +
            "<b>Records:</b> " + df_map['RECORD_COUNT'].astype(str) + "<br>" +
            "<b>Approach:</b> " + df_map['APPROACH'].astype(str) + "<br>" +
            "<b>Valid Geometry:</b> " + df_map['VALID_GEOMETRY'].astype(str)
        )
    
    with time_block("Create Plotly scatter mapbox"):
        # Create the map using scatter_mapbox (much faster than Folium)
        fig = px.scatter_mapbox(
            df_map,
            lat='LATITUDE',
            lon='LONGITUDE',
            size='marker_size',
            color='color_category',
            hover_name='ID',
            hover_data={'LATITUDE': False, 'LONGITUDE': False, 'marker_size': False, 'color_category': False},
            custom_data=['ID'],  # For click handling
            color_discrete_map={
                'Good (<30s)': 'green',
                'Fair (30-60s)': 'yellow', 
                'Poor (60-120s)': 'orange',
                'Critical (>120s)': 'red'
            },
            mapbox_style='open-street-map',
            height=500,
            title="Traffic Signals - Travel Time Analysis"
        )
        
        # Update hover template to use our custom text
        fig.update_traces(
            hovertemplate=df_map['hover_text'] + "<extra></extra>",
            marker=dict(
                sizemode='diameter',
                sizemin=4,
                opacity=0.7
            )
        )
        
        # Calculate proper zoom level based on data spread
        lat_range = df_map['LATITUDE'].max() - df_map['LATITUDE'].min()
        lon_range = df_map['LONGITUDE'].max() - df_map['LONGITUDE'].min()
        max_range = max(lat_range, lon_range)
        
        # Determine zoom level based on data spread
        if max_range > 1.0:
            zoom_level = 8
        elif max_range > 0.5:
            zoom_level = 9
        elif max_range > 0.2:
            zoom_level = 10
        elif max_range > 0.1:
            zoom_level = 11
        else:
            zoom_level = 12
        
        # Update layout for better performance and functionality
        fig.update_layout(
            mapbox=dict(
                center=dict(
                    lat=df_map['LATITUDE'].mean(),
                    lon=df_map['LONGITUDE'].mean()
                ),
                zoom=zoom_level,
                style='open-street-map'
            ),
            margin=dict(t=50, b=0, l=0, r=0),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right", 
                x=1
            )
        )
        
        # Enable zoom and pan interactions
        fig.update_layout(
            dragmode='pan'  # Enable panning
        )
    
    return fig


@time_function("create_travel_time_chart")
def create_travel_time_chart(travel_time_df, selected_signal=None):
    """Create a time series chart showing aggregated travel times."""
    
    if travel_time_df.empty:
        return None
    
    # Determine title based on selection
    if selected_signal:
        title = f"Total Travel Time for Signal {selected_signal}"
    else:
        title = "Total Travel Time - All Selected Signals"
    
    # Create a simple line chart with the aggregated data
    fig = go.Figure()
    
    # Add the single aggregated travel time series
    fig.add_trace(
        go.Scatter(
            x=travel_time_df['TIMESTAMP'],
            y=travel_time_df['TOTAL_TRAVEL_TIME_SECONDS'],
            mode='lines+markers',
            name='Total Travel Time',
            line=dict(color='blue', width=2),
            marker=dict(size=4),
            hovertemplate='<b>Total Travel Time</b><br>Time: %{x}<br>Travel Time: %{y:.1f}s<extra></extra>'
        )
    )
    
    # Update layout
    fig.update_layout(
        title=title,
        xaxis_title='Timestamp',
        yaxis_title='Total Travel Time (seconds)',
        height=500,
        showlegend=True,
        hovermode='x unified'
    )
    
    return fig


def render_travel_time_page(session, signals_df, filters):
    """Render the travel time analysis page."""
    
    with time_block("=== TRAVEL TIME PAGE RENDER START ==="):
        st.header("📊 Travel Time Analysis")
        
        # Show current filters info
        with st.expander("Current Filter Settings", expanded=False):
            st.write(f"**Date Range:** {filters['start_date']} to {filters['end_date']}")
            st.write(f"**Approach:** {filters['approach']}")
            st.write(f"**Valid Geometry:** {filters['valid_geometry']}")
            st.write(f"**Selected Signals:** {len(filters['signal_ids']) if filters['signal_ids'] else 'All'}")
        
        # Load travel time summary data for map
        with st.spinner("Loading travel time data..."):
            with time_block("Database query: get_travel_time_summary"):
                # Use cached version to avoid redundant queries
                summary_df = cached_get_travel_time_summary(
                    str(id(session)),  # Simple session identifier for caching
                    filters['start_date'],
                    filters['end_date'],
                    tuple(filters['signal_ids']) if filters['signal_ids'] else None,  # Make hashable for cache
                    filters['approach'],
                    filters['valid_geometry']
                )
            log_performance(f"Loaded {len(summary_df)} travel time summary records")
    
    if summary_df.empty:
        st.warning("No travel time data found for the selected filters.")
        return
    
    # Create and display map
    st.subheader("🗺️ Traffic Signals Map")
    st.markdown("*Bubble size represents total travel time, color represents average travel time*")
    
    with time_block("Create and render Plotly map"):
        travel_map = create_travel_time_map_plotly(summary_df)
        
        if travel_map:
            with time_block("Streamlit plotly_chart widget render"):
                # Display Plotly map with full interactivity enabled
                clicked_data = st.plotly_chart(
                    travel_map,
                    use_container_width=True,
                    key="travel_time_map",
                    config={
                        'displayModeBar': True,
                        'displaylogo': False,
                        'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                        'scrollZoom': True,  # Explicitly enable scroll zoom
                        'doubleClick': 'reset+autosize'  # Double-click to reset zoom
                    }
                )
            
            # Create a selectbox for signal selection (since Plotly click events are complex in Streamlit)
            st.subheader("🎯 Signal Selection")
            
            with time_block("Streamlit selectbox widget render"):
                signal_options = ['All Signals'] + sorted(summary_df['ID'].astype(str).tolist())
                
                selected_signal_dropdown = st.selectbox(
                    "Select a specific signal to analyze:",
                    options=signal_options,
                    index=0,
                    key="signal_selector"
                )
            
            # Set selected signal based on dropdown
            if selected_signal_dropdown != 'All Signals':
                selected_signal = selected_signal_dropdown
                st.session_state.selected_signal_from_map = selected_signal
            else:
                selected_signal = None
                if hasattr(st.session_state, 'selected_signal_from_map'):
                    del st.session_state.selected_signal_from_map
            # Provide feedback on selection
            if selected_signal:
                signal_info = summary_df[summary_df['ID'] == selected_signal]
                if not signal_info.empty:
                    st.success(f"✅ Analyzing Signal: {selected_signal}")
                    
                    # Show some key stats
                    with time_block("Streamlit metrics widgets render"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Travel Time", f"{signal_info.iloc[0]['TOTAL_TRAVEL_TIME']:.0f}s")
                        with col2:
                            st.metric("Average Travel Time", f"{signal_info.iloc[0]['AVG_TRAVEL_TIME']:.1f}s")
                        with col3:
                            st.metric("Records", f"{signal_info.iloc[0]['RECORD_COUNT']}")
            else:
                st.info("📊 Showing data for all selected signals")
    
    # Load aggregated travel time data for chart
    st.subheader("📈 Travel Time Time Series")
    
    with st.spinner("Loading aggregated travel time data..."):
        with time_block("Database query: get_travel_time_aggregated"):
            # Use cached version to avoid redundant queries
            travel_time_df = cached_get_travel_time_aggregated(
                str(id(session)),  # Simple session identifier for caching
                filters['start_date'],
                filters['end_date'],
                tuple([selected_signal] if selected_signal else filters['signal_ids']) if (selected_signal or filters['signal_ids']) else None,
                filters['approach'],
                filters['valid_geometry']
            )
        log_performance(f"Loaded {len(travel_time_df)} aggregated travel time records")
    
    if not travel_time_df.empty:
        # Create and display chart
        chart = create_travel_time_chart(travel_time_df, selected_signal)
        if chart:
            with time_block("Streamlit time series chart render"):
                st.plotly_chart(chart, use_container_width=True)
        
    else:
        st.warning("No aggregated travel time data available for the current selection.")
    
    # Clear selection button
    if selected_signal:
        if st.button("Clear Signal Selection", key="clear_selection"):
            if hasattr(st.session_state, 'selected_signal_from_map'):
                del st.session_state.selected_signal_from_map
            st.rerun()
        
    log_performance("=== TRAVEL TIME PAGE RENDER COMPLETE ===", 0)