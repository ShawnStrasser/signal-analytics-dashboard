"""
Anomalies Analysis Page
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
from utils.database import get_travel_time_data, get_anomaly_summary, get_anomaly_aggregated
from utils.performance import time_function, time_block, log_performance
from utils.session_state import render_anomaly_type_filter


def create_anomaly_map(anomaly_df, anomaly_type="All"):
    """Create a folium map with anomaly visualizations."""
    
    if anomaly_df.empty:
        return None
    
    # Calculate center of map
    center_lat = anomaly_df['LATITUDE'].mean()
    center_lon = anomaly_df['LONGITUDE'].mean()
    
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=10,
        tiles='OpenStreetMap'
    )
    
    # Select the appropriate count column based on anomaly type
    count_column = 'POINT_SOURCE_COUNT' if anomaly_type == "Point Source" else 'ANOMALY_COUNT'
    
    # Filter out rows with zero counts
    display_df = anomaly_df[anomaly_df[count_column] > 0].copy()
    
    if display_df.empty:
        return m
    
    # Normalize bubble sizes
    max_count = display_df[count_column].max()
    min_count = display_df[count_column].min()
    
    # Add markers for each signal
    for _, row in display_df.iterrows():
        # Calculate bubble size (normalize between 15 and 60 pixels)
        if max_count > min_count:
            normalized_size = 15 + (row[count_column] - min_count) / (max_count - min_count) * 45
        else:
            normalized_size = 30
        # Color based on anomaly intensity
        count = row[count_column]
        if count < 5:
            color = 'yellow'
        elif count < 15:
            color = 'orange'
        else:
            color = 'red'
        # Create popup text
        popup_text = f"""
        <b>Signal ID:</b> {row['ID']}<br>
        <b>Total Anomalies:</b> {row['ANOMALY_COUNT']}<br>
        <b>Point Source Anomalies:</b> {row['POINT_SOURCE_COUNT']}<br>
        <b>Approach:</b> {row['APPROACH']}<br>
        <b>Valid Geometry:</b> {row['VALID_GEOMETRY']}
        """
        
        folium.CircleMarker(
            location=[row['LATITUDE'], row['LONGITUDE']],
            radius=normalized_size,
            color=color,
            fillColor=color,
            fillOpacity=0.7,
            popup=folium.Popup(popup_text, max_width=300),
            tooltip=f"Signal {row['ID']} ({count} anomalies)"
        ).add_to(m)
    
    return m


def create_anomaly_chart(anomaly_aggregated_df, selected_signal=None):
    """Create a dual-series chart showing aggregated actual vs predicted travel times."""
    
    if anomaly_aggregated_df.empty:
        return None
    
    # Determine title based on selection
    if selected_signal:
        title = f"Total Travel Time vs Prediction - Signal {selected_signal}"
    else:
        title = "Total Travel Time vs Prediction - All Selected Signals"
    
    # Create the plot
    fig = go.Figure()
    
    # Add actual travel time series
    fig.add_trace(
        go.Scatter(
            x=anomaly_aggregated_df['TIMESTAMP'],
            y=anomaly_aggregated_df['TOTAL_ACTUAL_TRAVEL_TIME'],
            mode='lines+markers',
            name='Actual Travel Time',
            line=dict(color='blue', width=2),
            marker=dict(size=4),
            hovertemplate='<b>Actual</b><br>Time: %{x}<br>Total Travel Time: %{y:.1f}s<extra></extra>'
        )
    )
    
    # Add predicted travel time series
    fig.add_trace(
        go.Scatter(
            x=anomaly_aggregated_df['TIMESTAMP'],
            y=anomaly_aggregated_df['TOTAL_PREDICTION'],
            mode='lines+markers',
            name='Predicted Travel Time',
            line=dict(color='green', width=2, dash='dash'),
            marker=dict(size=4),
            hovertemplate='<b>Predicted</b><br>Time: %{x}<br>Total Travel Time: %{y:.1f}s<extra></extra>'
        )
    )
    
    # Update layout
    fig.update_layout(
        title=title,
        xaxis_title='Timestamp',
        yaxis_title='Total Travel Time (seconds)',
        height=500,
        showlegend=True,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig


def render_anomalies_page(session, signals_df, filters):
    """Render the anomalies analysis page."""
    
    st.header("🚨 Anomaly Analysis")
    
    # Add anomaly type filter to sidebar (this adds to the existing filters)
    with st.sidebar:
        st.markdown("---")
        render_anomaly_type_filter()
    
    # Get updated filters including anomaly type
    from utils.session_state import get_filter_values
    filters = get_filter_values()
    
    # Show current filters info
    with st.expander("Current Filter Settings", expanded=False):
        st.write(f"**Date Range:** {filters['start_date']} to {filters['end_date']}")
        st.write(f"**Approach:** {filters['approach']}")
        st.write(f"**Valid Geometry:** {filters['valid_geometry']}")
        st.write(f"**Selected Signals:** {len(filters['signal_ids']) if filters['signal_ids'] else 'All'}")
        st.write(f"**Anomaly Type:** {filters['anomaly_type']}")
    
    # Load anomaly summary data for map
    with st.spinner("Loading anomaly data..."):
        anomaly_df = get_anomaly_summary(
            session,
            filters['start_date'],
            filters['end_date'],
            filters['signal_ids'],
            filters['approach'],
            filters['valid_geometry'],
            filters['anomaly_type']
        )
    
    if anomaly_df.empty:
        st.warning("No anomaly data found for the selected filters.")
        return
    
    # Create and display map
    st.subheader("🗺️ Anomaly Distribution Map")
    st.markdown(f"*Bubble size represents number of {filters['anomaly_type'].lower()} anomalies*")
    
    anomaly_map = create_anomaly_map(anomaly_df, filters['anomaly_type'])
    
    if anomaly_map:
        # Display map and capture interactions
        map_data = st_folium(
            anomaly_map,
            width=700,
            height=500,
            returned_objects=["last_object_clicked"]
        )
        
        # Check if a marker was clicked
        selected_signal = None
        if map_data['last_object_clicked']:
            clicked_tooltip = map_data['last_object_clicked'].get('tooltip')
            if clicked_tooltip and 'Signal ' in clicked_tooltip:
                selected_signal = clicked_tooltip.split(' ')[1]
                st.session_state.selected_signal_from_map = selected_signal
        elif st.session_state.selected_signal_from_map:
            selected_signal = st.session_state.selected_signal_from_map
        
        # Maintain selection feedback without summary metrics
        if selected_signal:
            signal_info = anomaly_df[anomaly_df['ID'] == selected_signal]
            if not signal_info.empty:
                st.success(f"Selected Signal: {selected_signal}")
    
    # Load aggregated anomaly data for chart
    st.subheader("📈 Travel Time Analysis with Anomaly Detection")
    
    with st.spinner("Loading aggregated anomaly data..."):
        anomaly_aggregated_df = get_anomaly_aggregated(
            session,
            filters['start_date'],
            filters['end_date'],
            [selected_signal] if selected_signal else filters['signal_ids'],
            filters['approach'],
            filters['valid_geometry']
        )
    
    if not anomaly_aggregated_df.empty:
        # Create and display chart
        chart = create_anomaly_chart(anomaly_aggregated_df, selected_signal)
        if chart:
            st.plotly_chart(chart, use_container_width=True)
        
        # Load detailed travel time data for anomaly details table
        with st.spinner("Loading anomaly details..."):
            travel_time_df = get_travel_time_data(
                session,
                filters['start_date'],
                filters['end_date'],
                [selected_signal] if selected_signal else filters['signal_ids'],
                filters['approach'],
                filters['valid_geometry']
            )
        
        # Anomaly analysis table
        st.subheader("📋 Anomaly Details")
        
        if not travel_time_df.empty:
            if selected_signal:
                signal_data = travel_time_df[travel_time_df['ID'] == selected_signal]
            else:
                signal_data = travel_time_df
            
            # Show anomalies
            anomalies = signal_data[signal_data['ANOMALY'] == True].copy()
            
            if not anomalies.empty:
                # Format the anomaly data for display
                display_anomalies = anomalies[['TIMESTAMP', 'ID', 'TRAVEL_TIME_SECONDS', 'PREDICTION', 'ORIGINATED_ANOMALY']].copy()
                display_anomalies['TIMESTAMP'] = display_anomalies['TIMESTAMP'].dt.strftime('%Y-%m-%d %H:%M:%S')
                display_anomalies['TRAVEL_TIME_SECONDS'] = display_anomalies['TRAVEL_TIME_SECONDS'].round(1)
                display_anomalies['PREDICTION'] = display_anomalies['PREDICTION'].round(1) if 'PREDICTION' in display_anomalies.columns else None
                
                # Rename columns for better display
                display_anomalies = display_anomalies.rename(columns={
                    'TIMESTAMP': 'Timestamp',
                    'ID': 'Signal ID',
                    'TRAVEL_TIME_SECONDS': 'Actual (sec)',
                    'PREDICTION': 'Predicted (sec)',
                    'ORIGINATED_ANOMALY': 'Point Source'
                })
                
                st.dataframe(
                    display_anomalies,
                    use_container_width=True,
                    hide_index=True
                )
                
                # Download button for anomaly data
                csv = display_anomalies.to_csv(index=False)
                st.download_button(
                    label="Download Anomaly Data as CSV",
                    data=csv,
                    file_name=f"anomalies_{filters['start_date']}_{filters['end_date']}.csv",
                    mime="text/csv"
                )
            else:
                st.info("No anomalies found for the current selection.")
        else:
            st.warning("No anomaly details available for the current selection.")
    else:
        st.warning("No aggregated anomaly data available for the current selection.")
    
    # Clear selection button
    if selected_signal:
        if st.button("Clear Signal Selection"):
            st.session_state.selected_signal_from_map = None
            st.rerun()