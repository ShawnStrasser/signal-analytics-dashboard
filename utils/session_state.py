"""
Session state management for shared filters across pages.
"""

import streamlit as st
from datetime import datetime, timedelta


def initialize_session_state():
    """Initialize default session state values."""
    
    # Default date range (last 7 days)
    default_end_date = datetime.now().date()
    default_start_date = default_end_date - timedelta(days=7)
    
    # Initialize session state variables if they don't exist
    if 'start_date' not in st.session_state:
        st.session_state.start_date = default_start_date
    
    if 'end_date' not in st.session_state:
        st.session_state.end_date = default_end_date
    
    if 'approach_filter' not in st.session_state:
        st.session_state.approach_filter = "All"
    
    if 'valid_geometry_filter' not in st.session_state:
        st.session_state.valid_geometry_filter = "All"
    
    if 'selected_signals' not in st.session_state:
        st.session_state.selected_signals = []
    
    if 'anomaly_type_filter' not in st.session_state:
        st.session_state.anomaly_type_filter = "All"
    
    if 'selected_signal_from_map' not in st.session_state:
        st.session_state.selected_signal_from_map = None


def render_common_filters(signals_df):
    """Render the common filters that appear on both pages."""
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Date range slider
        st.subheader("Date Range")
        start_date = st.date_input(
            "Start Date",
            value=st.session_state.start_date,
            key='start_date_input'
        )
        end_date = st.date_input(
            "End Date", 
            value=st.session_state.end_date,
            key='end_date_input'
        )
        
        # Update session state
        st.session_state.start_date = start_date
        st.session_state.end_date = end_date
    
    with col2:
        st.subheader("Filters")
        
        # Approach filter
        approach_options = ["All", "True", "False"]
        approach_filter = st.selectbox(
            "Approach",
            approach_options,
            index=approach_options.index(st.session_state.approach_filter),
            key='approach_selectbox'
        )
        st.session_state.approach_filter = approach_filter
        
        # Valid Geometry filter
        geometry_options = ["All", "True", "False"]
        geometry_filter = st.selectbox(
            "Valid Geometry",
            geometry_options,
            index=geometry_options.index(st.session_state.valid_geometry_filter),
            key='geometry_selectbox'
        )
        st.session_state.valid_geometry_filter = geometry_filter
    
    # Signal selector (full width)
    st.subheader("Traffic Signals")
    
    if not signals_df.empty:
        # Get all signal IDs for multiselect
        all_signal_ids = sorted(signals_df['ID'].dropna().unique().tolist())
        
        # Default to all selected if none are selected
        if not st.session_state.selected_signals:
            default_selection = all_signal_ids
        else:
            default_selection = st.session_state.selected_signals
        
        selected_signals = st.multiselect(
            "Select Traffic Signals",
            options=all_signal_ids,
            default=default_selection,
            key='signals_multiselect'
        )
        
        st.session_state.selected_signals = selected_signals
    else:
        st.warning("No signal data available")
        st.session_state.selected_signals = []


def get_filter_values():
    """Return current filter values as a dictionary."""
    
    # Convert filter strings to boolean values where needed
    approach_value = None
    if st.session_state.approach_filter == "True":
        approach_value = True
    elif st.session_state.approach_filter == "False":
        approach_value = False
    
    geometry_value = None
    if st.session_state.valid_geometry_filter == "True":
        geometry_value = True
    elif st.session_state.valid_geometry_filter == "False":
        geometry_value = False
    
    return {
        'start_date': st.session_state.start_date,
        'end_date': st.session_state.end_date,
        'approach': approach_value,
        'valid_geometry': geometry_value,
        'signal_ids': st.session_state.selected_signals if st.session_state.selected_signals else None,
        'anomaly_type': st.session_state.anomaly_type_filter
    }


def render_anomaly_type_filter():
    """Render the anomaly type filter specific to the anomalies page."""
    
    anomaly_options = ["All", "Point Source"]
    anomaly_filter = st.selectbox(
        "Anomaly Type",
        anomaly_options,
        index=anomaly_options.index(st.session_state.anomaly_type_filter),
        key='anomaly_type_selectbox'
    )
    st.session_state.anomaly_type_filter = anomaly_filter