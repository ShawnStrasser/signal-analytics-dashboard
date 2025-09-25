"""
Signal Analytics Dashboard - Main Application
"""

import streamlit as st
from utils.database import get_snowflake_session, get_signals_data
from utils.session_state import initialize_session_state, render_common_filters, get_filter_values
from utils.performance import time_block, log_performance

# Configure the page
st.set_page_config(
    page_title="Signal Analytics Dashboard",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    """Main application entry point."""
    
    # Initialize session state
    initialize_session_state()
    
    # Get Snowflake session
    session = get_snowflake_session()
    
    if session is None:
        st.error("Unable to connect to Snowflake. Please check your connection settings.")
        st.stop()
    
    # App header
    st.title("🚦 Signal Analytics Dashboard")
    st.markdown("---")
    
    # Load signals data for filters
    with st.spinner("Loading traffic signals data..."):
        with time_block("Database query: get_signals_data"):
            signals_df = get_signals_data(session)
        log_performance(f"Loaded {len(signals_df)} signals from database")
    
    if signals_df.empty:
        st.error("No signal data available. Please check your database connection.")
        st.stop()
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Select Page",
        ["Travel Time", "Anomalies"],
        key="navigation_radio"
    )
    
    # Sidebar filters (common to both pages)
    st.sidebar.markdown("---")
    st.sidebar.subheader("Filters")
    
    # Render filters in sidebar
    with st.sidebar:
        render_common_filters(signals_df)
    
    # Show current filter values for debugging
    filters = get_filter_values()
    
    # Page routing
    with time_block(f"=== LOADING {page.upper()} PAGE ==="):
        if page == "Travel Time":
            from routes.travel_time import render_travel_time_page
            render_travel_time_page(session, signals_df, filters)
        elif page == "Anomalies":
            from routes.anomalies import render_anomalies_page
            render_anomalies_page(session, signals_df, filters)
    
    log_performance("=== PAGE ROUTING COMPLETE ===", 0)


if __name__ == "__main__":
    main()