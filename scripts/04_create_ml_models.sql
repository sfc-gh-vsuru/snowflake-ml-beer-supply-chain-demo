-- ============================================================
-- 04_create_ml_models.sql
-- Builds all Snowflake ML models and persists their outputs.
-- Requires SNOWFLAKE.ML privileges on the ML schema.
-- ============================================================

USE ROLE IDENTIFIER($DEMO_ROLE);
USE WAREHOUSE IDENTIFIER($DEMO_WAREHOUSE);

-- ============================================================
-- 1. Inventory Forecast (Snowflake ML Forecast)
--    Predicts inventory levels 12 weeks out per distribution center.
-- ============================================================
CREATE OR REPLACE SNOWFLAKE.ML.FORECAST BEERCOMPANYDEMO.ML.INVENTORY_FORECAST_MODEL(
    INPUT_DATA => SYSTEM$REFERENCE('VIEW', 'BEERCOMPANYDEMO.ANALYTICS.V_INVENTORY_FORECAST_INPUT'),
    SERIES_COLNAME => 'SERIES',
    TIMESTAMP_COLNAME => 'DS',
    TARGET_COLNAME => 'Y'
);

CREATE OR REPLACE TABLE BEERCOMPANYDEMO.ML.INVENTORY_FORECAST AS
SELECT * FROM TABLE(
    BEERCOMPANYDEMO.ML.INVENTORY_FORECAST_MODEL!FORECAST(
        FORECASTING_PERIODS => 12,
        CONFIG_OBJECT => {'prediction_interval': 0.90}
    )
);

-- ============================================================
-- 2. Raw Material Price Forecast (Snowflake ML Forecast)
--    Predicts barley and hops prices 12 weeks out.
-- ============================================================
CREATE OR REPLACE SNOWFLAKE.ML.FORECAST BEERCOMPANYDEMO.ML.PRICE_FORECAST_MODEL(
    INPUT_DATA => SYSTEM$REFERENCE('VIEW', 'BEERCOMPANYDEMO.ANALYTICS.V_PRICE_FORECAST_INPUT'),
    SERIES_COLNAME => 'SERIES',
    TIMESTAMP_COLNAME => 'DS',
    TARGET_COLNAME => 'Y'
);

CREATE OR REPLACE TABLE BEERCOMPANYDEMO.ML.PRICE_FORECAST AS
SELECT * FROM TABLE(
    BEERCOMPANYDEMO.ML.PRICE_FORECAST_MODEL!FORECAST(
        FORECASTING_PERIODS => 12,
        CONFIG_OBJECT => {'prediction_interval': 0.90}
    )
);

-- ============================================================
-- 3. Lead Time Anomaly Detection (Snowflake ML Anomaly Detection)
--    Flags shipments where lead times are abnormally high.
-- ============================================================
CREATE OR REPLACE SNOWFLAKE.ML.ANOMALY_DETECTION BEERCOMPANYDEMO.ML.LEAD_TIME_ANOMALY_MODEL(
    INPUT_DATA => SYSTEM$REFERENCE('VIEW', 'BEERCOMPANYDEMO.ANALYTICS.V_ANOMALY_TRAIN'),
    SERIES_COLNAME => 'SERIES',
    TIMESTAMP_COLNAME => 'DS',
    TARGET_COLNAME => 'Y',
    LABEL_COLNAME => ''
);

CREATE OR REPLACE TABLE BEERCOMPANYDEMO.ML.LEAD_TIME_ANOMALIES AS
SELECT * FROM TABLE(
    BEERCOMPANYDEMO.ML.LEAD_TIME_ANOMALY_MODEL!DETECT_ANOMALIES(
        INPUT_DATA => SYSTEM$REFERENCE('VIEW', 'BEERCOMPANYDEMO.ANALYTICS.V_ANOMALY_TEST'),
        SERIES_COLNAME => 'SERIES',
        TIMESTAMP_COLNAME => 'DS',
        TARGET_COLNAME => 'Y',
        CONFIG_OBJECT => {'prediction_interval': 0.95}
    )
);

-- ============================================================
-- 4. Margin Driver Analysis (Snowflake ML Top Insights)
--    Identifies which factors (barley price, hops price, beer style,
--    DC location) most influence margin changes.
-- ============================================================
CREATE OR REPLACE SNOWFLAKE.ML.TOP_INSIGHTS BEERCOMPANYDEMO.ML.MARGIN_INSIGHTS();

-- Run the analysis and save results
CALL BEERCOMPANYDEMO.ML.MARGIN_INSIGHTS!GET_DRIVERS(
    INPUT_DATA => TABLE(BEERCOMPANYDEMO.ANALYTICS.V_MARGIN_DRIVERS_INPUT),
    LABEL_COLNAME => 'LABEL',
    METRIC_COLNAME => 'METRIC'
);

CREATE OR REPLACE TABLE BEERCOMPANYDEMO.ML.MARGIN_DRIVER_RESULTS AS
SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
