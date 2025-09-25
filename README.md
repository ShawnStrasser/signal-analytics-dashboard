# signal-analytics-dashboard
Dashboard to visualize traffic signal travel time analytics.

## Database Schema Reference

### Snowflake Connection
Two connection methods are supported:
1. Using active session (preferred): `from snowflake.snowpark.context import get_active_session`
2. Using connection parameters: `from snowflake.snowpark.session import Session`

### Table Definitions

#### DIM_SIGNALS_XD
```sql
CREATE TABLE TPAU_DB.TPAU_RITIS_SCHEMA.DIM_SIGNALS_XD (
    ID VARCHAR,
    latitude DOUBLE,
    longitude DOUBLE,
    valid_geometry BOOLEAN,
    XD INT,
    bearing VARCHAR,
    county VARCHAR,
    roadName VARCHAR,
    miles DOUBLE,
    approach BOOLEAN,
    extended BOOLEAN
);
```

#### TRAVEL_TIME_ANALYTICS
```sql
CREATE OR REPLACE TABLE TRAVEL_TIME_ANALYTICS (
    XD INT,
    TIMESTAMP TIMESTAMP,
    TRAVEL_TIME_SECONDS NUMBER,
    prediction NUMBER,
    anomaly BOOLEAN,
    originated_anomaly BOOLEAN
);
```

#### CHANGEPOINTS
```sql
CREATE TABLE CHANGEPOINTS (
    XD INTEGER,
    TIMESTAMP TIMESTAMP,
    SCORE FLOAT,
    AVG_BEFORE FLOAT,
    AVG_AFTER FLOAT,
    AVG_DIFF FLOAT,
    PCT_CHANGE FLOAT
);
```

#### FREEFLOW
```sql
CREATE TABLE FREEFLOW (
    XD INTEGER,
    TRAVEL_TIME_SECONDS FLOAT
);
```

## Running the App

### Prerequisites
- Python 3.8 or higher
- Access to Snowflake database with the required tables
- Snowflake connection configured (see connection methods below)

### Installation

1. Clone the repository and navigate to the project directory:
   ```bash
   cd signal-analytics-dashboard
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your Snowflake connection (choose one method):
   
   **Method 1: Active Session (Preferred)**
   - Ensure you have an active Snowflake session in your environment
   - The app will automatically detect and use the active session

   **Method 2: Connection Parameters**
   - Set the `SNOWFLAKE_CONNECTION` environment variable with your connection details:
   ```bash
   export SNOWFLAKE_CONNECTION='{"account":"your_account","user":"your_user","password":"your_password","warehouse":"your_warehouse","database":"your_database","schema":"your_schema"}'
   ```

4. Run the application:
   ```bash
   streamlit run main.py
   ```
   
   Or use the provided startup scripts:
   - Windows: `run.bat`
   - Linux/Mac: `./run.sh`

### Features

#### Travel Time Page
- **Interactive Map**: Visualize traffic signals with bubble size representing total travel time and color indicating average travel time
- **Time Series Chart**: Analyze travel time trends over time with anomaly highlighting
- **Filters**: Date range, approach type, valid geometry, and signal selection
- **Interactive Selection**: Click on map markers to filter the time series chart
- **Summary Statistics**: Key metrics including averages, anomaly counts, and record counts

#### Anomalies Page  
- **Anomaly Map**: Shows signals sized by anomaly count with color-coded intensity
- **Dual-Series Chart**: Compare actual vs predicted travel times with anomaly highlighting
- **Anomaly Types**: Filter between "All" anomalies and "Point Source" anomalies
- **Detailed Analysis**: Downloadable anomaly data table with timestamps and predictions
- **Cross-Page State**: All filters persist when switching between pages

### Project Structure
```
signal-analytics-dashboard/
├── main.py                 # Main application entry point
├── config.py              # Application configuration
├── requirements.txt       # Python dependencies
├── pages/
│   ├── travel_time.py    # Travel time analysis page
│   ├── anomalies.py      # Anomaly analysis page
│   └── __init__.py
└── utils/
    ├── database.py       # Snowflake connection and queries
    ├── session_state.py  # Cross-page state management
    └── __init__.py
```
