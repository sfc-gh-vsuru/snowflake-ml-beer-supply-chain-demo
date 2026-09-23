#!/usr/bin/env bash
# ============================================================
# setup.sh - One-command setup for Beer Co. Supply Chain Demo
#
# Prerequisites:
#   1. Snowflake CLI (snow) installed and a connection configured
#      Install: https://docs.snowflake.com/en/developer-guide/snowflake-cli/index
#      Configure: snow connection add
#   2. A Snowflake role with CREATE DATABASE, CREATE SNOWFLAKE.ML.* privileges
#   3. A warehouse to use for queries and ML model training
#
# Usage:
#   ./setup.sh --connection <name> --role <role> --warehouse <warehouse>
#
# Example:
#   ./setup.sh --connection my_conn --role SYSADMIN --warehouse COMPUTE_WH
# ============================================================

set -euo pipefail

# ── Parse arguments ──
CONNECTION=""
ROLE=""
WAREHOUSE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --connection) CONNECTION="$2"; shift 2;;
        --role)       ROLE="$2";       shift 2;;
        --warehouse)  WAREHOUSE="$2";  shift 2;;
        -h|--help)
            echo "Usage: ./setup.sh --connection <name> --role <role> --warehouse <warehouse>"
            echo ""
            echo "  --connection   Snowflake CLI connection name (from 'snow connection list')"
            echo "  --role         Snowflake role with CREATE DATABASE privileges"
            echo "  --warehouse    Warehouse for queries and ML model training"
            exit 0;;
        *) echo "Unknown argument: $1"; exit 1;;
    esac
done

if [[ -z "$CONNECTION" || -z "$ROLE" || -z "$WAREHOUSE" ]]; then
    echo "ERROR: All arguments required."
    echo "Usage: ./setup.sh --connection <name> --role <role> --warehouse <warehouse>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SNOW="snow --connection $CONNECTION"

run_sql() {
    echo "  Running: $1"
    $SNOW sql -q "$1" --format json > /dev/null 2>&1 || {
        echo "  WARNING: Statement may have had an issue, continuing..."
    }
}

run_sql_file() {
    echo "  Executing: $1"
    # Set session variables then run the file
    $SNOW sql -q "SET DEMO_ROLE = '$ROLE'; SET DEMO_WAREHOUSE = '$WAREHOUSE';" > /dev/null 2>&1
    $SNOW sql \
        --variable "DEMO_ROLE=$ROLE" \
        --variable "DEMO_WAREHOUSE=$WAREHOUSE" \
        -f "$1" > /dev/null 2>&1 || {
        echo "  WARNING: Some statements in $1 may have had issues, continuing..."
    }
}

echo "============================================================"
echo "Beer Co. Supply Chain Demo - Setup"
echo "============================================================"
echo "Connection:  $CONNECTION"
echo "Role:        $ROLE"
echo "Warehouse:   $WAREHOUSE"
echo ""

# ── Step 1: Create database, schemas, tables ──
echo "[1/6] Creating database, schemas, and tables..."
run_sql_file "$SCRIPT_DIR/scripts/01_setup_database.sql"
echo "  Done."

# ── Step 2: Upload CSV data to stage ──
echo "[2/6] Uploading CSV data files to Snowflake stage..."
run_sql "CREATE OR REPLACE FILE FORMAT BEERCOMPANYDEMO.ANALYTICS.CSV_FORMAT TYPE = CSV FIELD_OPTIONALLY_ENCLOSED_BY = '\"' SKIP_HEADER = 1 NULL_IF = ('NULL', '') EMPTY_FIELD_AS_NULL = TRUE"
run_sql "CREATE OR REPLACE STAGE BEERCOMPANYDEMO.ANALYTICS.DATA_STAGE FILE_FORMAT = BEERCOMPANYDEMO.ANALYTICS.CSV_FORMAT"

for csv_file in "$SCRIPT_DIR"/data/*.csv; do
    filename=$(basename "$csv_file")
    echo "    Uploading $filename..."
    $SNOW stage copy "$csv_file" @BEERCOMPANYDEMO.ANALYTICS.DATA_STAGE --overwrite > /dev/null 2>&1
done
echo "  Done."

# ── Step 3: Load data into tables ──
echo "[3/6] Loading data into tables (COPY INTO)..."
run_sql_file "$SCRIPT_DIR/scripts/02_load_data.sql"
echo "  Done."

# ── Step 4: Create views for ML ──
echo "[4/6] Creating analytics views..."
run_sql_file "$SCRIPT_DIR/scripts/03_create_views.sql"
echo "  Done."

# ── Step 5: Build ML models ──
echo "[5/6] Building Snowflake ML models (this may take 2-3 minutes)..."
run_sql_file "$SCRIPT_DIR/scripts/04_create_ml_models.sql"
echo "  Done."

# ── Step 6: Deploy Streamlit app ──
echo "[6/6] Deploying Streamlit dashboard..."
# Upload app file to Streamlit stage
run_sql "CREATE OR REPLACE STAGE BEERCOMPANYDEMO.ANALYTICS.STREAMLIT_STAGE DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')"

$SNOW sql -q "PUT file://$SCRIPT_DIR/streamlit_app.py @BEERCOMPANYDEMO.ANALYTICS.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE" > /dev/null 2>&1

run_sql "CREATE OR REPLACE STREAMLIT BEERCOMPANYDEMO.ANALYTICS.BEER_SUPPLY_CHAIN_DASHBOARD ROOT_LOCATION = '@BEERCOMPANYDEMO.ANALYTICS.STREAMLIT_STAGE' MAIN_FILE = 'streamlit_app.py' QUERY_WAREHOUSE = '$WAREHOUSE' TITLE = 'Beer Co. Supply Chain and Pricing Intelligence'"

# Grants
run_sql "GRANT USAGE ON DATABASE BEERCOMPANYDEMO TO ROLE ACCOUNTADMIN"
run_sql "GRANT USAGE ON SCHEMA BEERCOMPANYDEMO.ANALYTICS TO ROLE ACCOUNTADMIN"
run_sql "GRANT USAGE ON SCHEMA BEERCOMPANYDEMO.ML TO ROLE ACCOUNTADMIN"
run_sql "GRANT USAGE ON SCHEMA BEERCOMPANYDEMO.BASE TO ROLE ACCOUNTADMIN"
run_sql "GRANT SELECT ON ALL TABLES IN SCHEMA BEERCOMPANYDEMO.ANALYTICS TO ROLE ACCOUNTADMIN"
run_sql "GRANT SELECT ON ALL VIEWS IN SCHEMA BEERCOMPANYDEMO.ANALYTICS TO ROLE ACCOUNTADMIN"
run_sql "GRANT SELECT ON ALL TABLES IN SCHEMA BEERCOMPANYDEMO.ML TO ROLE ACCOUNTADMIN"
run_sql "GRANT SELECT ON ALL TABLES IN SCHEMA BEERCOMPANYDEMO.BASE TO ROLE ACCOUNTADMIN"
run_sql "GRANT USAGE ON STREAMLIT BEERCOMPANYDEMO.ANALYTICS.BEER_SUPPLY_CHAIN_DASHBOARD TO ROLE ACCOUNTADMIN"
echo "  Done."

echo ""
echo "============================================================"
echo "Setup complete!"
echo ""
echo "Open the dashboard in Snowsight:"
echo "  Projects > Streamlit > BEERCOMPANYDEMO.ANALYTICS.BEER_SUPPLY_CHAIN_DASHBOARD"
echo "============================================================"
