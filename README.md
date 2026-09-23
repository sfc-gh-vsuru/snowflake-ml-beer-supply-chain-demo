# Beer Co. Supply Chain & Pricing Intelligence Demo

A Snowflake-native demo showcasing **Snowflake ML** for supply chain risk management and raw material pricing intelligence, built for the Coalesce webinar.

Two personas, one dashboard:
- **Supply Chain Risk Manager** -- disruption monitoring, inventory forecasting, anomaly detection
- **Beer Sales Head** -- commodity price forecasting, margin analysis, pricing recommendations

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url> && cd SupplyChainWebinar

# 2. Run the setup (creates everything in Snowflake)
./setup.sh --connection <your_connection> --role SYSADMIN --warehouse COMPUTE_WH

# 3. Open the dashboard in Snowsight
#    Projects > Streamlit > BEERCOMPANYDEMO.ANALYTICS.BEER_SUPPLY_CHAIN_DASHBOARD
```

Setup takes ~3-5 minutes (ML model training is the longest step).

## Prerequisites

| Requirement | Details |
|------------|---------|
| **Snowflake CLI** | v3.0+ installed. [Install guide](https://docs.snowflake.com/en/developer-guide/snowflake-cli/index). Run `snow --version` to check. |
| **CLI Connection** | A named connection configured via `snow connection add`. Run `snow connection list` to verify. |
| **Snowflake Role** | Needs: `CREATE DATABASE`, `CREATE SCHEMA`, `CREATE TABLE`, `CREATE STAGE`, `CREATE STREAMLIT`, `CREATE SNOWFLAKE.ML.FORECAST`, `CREATE SNOWFLAKE.ML.ANOMALY_DETECTION`, `CREATE SNOWFLAKE.ML.TOP_INSIGHTS`. `SYSADMIN` or equivalent works. |
| **Warehouse** | Any active warehouse. ML model training uses standard compute. |

## What Gets Created

### Database: `BEERCOMPANYDEMO`

| Schema | Contents |
|--------|----------|
| `BASE` | 3 tables -- product master, plant/DC reference, inventory baseline (copied from Coalesce data shares) |
| `ANALYTICS` | 11 tables + 6 views -- synthetic 2-year weekly data: sales, shipments, inventory, pricing, events, distribution network |
| `ML` | 4 ML model objects + 4 output tables -- forecasts, anomalies, margin driver analysis |

### Streamlit App: `BEER_SUPPLY_CHAIN_DASHBOARD`

Deployed as a classic Streamlit-in-Snowflake (SiS) app.

---

## Data Model

```
SUPPLIERS (6)              BREWERIES (3)           DISTRIBUTION CENTERS (6)        DISTRIBUTORS (14)
  Montana Barley    --->    Brooklyn Brewery  --->   DC-NYC (Brooklyn)         --->  Boston, Philly
  Dakota Grain      --->    Chicago Brewery   --->   DC-CHI (Chicago)          --->  Detroit, Minneapolis, St.Louis
  Yakima Hops       --->    Portland Brewery  --->   DC-ATL (Atlanta)          --->  Miami, Tampa, Nashville
  Idaho Barley                                       DC-DAL (Dallas)           --->  Houston, Denver, Phoenix
  Saskatchewan Grain                                 DC-SEA (Seattle)          --->  Portland, SF, LA
  Hallertau Hops (EU)                                DC-TOR (Toronto)
```

- **100 beer products** across 6 styles (Lager, IPA, Stout, Pilsner, Ale, generic Beer)
- **104 weeks** of data (Oct 2024 -- Sep 2026)
- **28 supply chain routes** with lat/lon coordinates
- **12 disruption events**: Ukraine grain war, Red Sea attacks, Hurricane Helene, Polar Vortex, Pacific NW wildfires, Gulf hurricane, Midwest drought, and more

---

## ML Models Explained

### 1. Inventory Forecast (Snowflake ML Forecast)

**What it does:** Predicts inventory levels at each distribution center for the next 12 weeks.

**How to read the chart:** Solid lines = actual inventory history. Dashed lines = ML forecast. Shaded bands = 90% confidence interval (the model is 90% sure the actual value will fall within this range). If the lower bound dips below current demand levels, that DC may face stockouts.

**Business value:** Lets the supply chain manager see which DCs are trending toward low inventory and need replenishment orders now, not after it's too late.

### 2. Raw Material Price Forecast (Snowflake ML Forecast)

**What it does:** Predicts barley and hops spot prices for the next 12 weeks.

**How to read the chart:** Same as above -- solid = actual, dashed = forecast, shaded = confidence band. The dashed baseline shows what prices would be without any disruption events. When the solid line spikes above the baseline, that's event-driven inflation.

**Business value:** The Sales Head can see whether current commodity price spikes are temporary or the new normal, and plan pricing strategy accordingly.

### 3. Lead Time Anomaly Detection (Snowflake ML Anomaly Detection)

**What it does:** Learns the "normal" pattern of delivery lead times across all routes and DCs, then flags weeks where lead times are abnormally high.

**How to read the chart:** Blue dots = normal lead times. Red dots = anomalies (the model flagged these as statistically unusual). Gray shaded area = the expected range. Any red dot above the gray band means something disrupted that route beyond what weather or seasonal patterns would explain.

**Business value:** Instead of manually monitoring hundreds of shipments, the system automatically surfaces the disruptions that need attention. If Toronto DC suddenly shows red dots, the risk manager knows to investigate immediately.

### 4. Margin Drivers / Top Insights (Snowflake ML Top Insights)

**What it does:** Compares margins in a recent period (Apr-Sep 2026) against the earlier baseline, and identifies which factors (barley price, hops price, beer style, DC location, volume) explain the difference.

**How to read the chart:** Horizontal bars show each driver's relative contribution to margin changes. Longer bars = bigger impact. Red bars = factors that hurt margins. Green bars = factors that helped. The top bar is always the most important driver.

**Business value:** Instead of guessing why margins changed, the model quantifies it. "Hops price above $4.79 accounts for 51% of the margin decline" is actionable -- the Sales Head knows exactly which input cost to hedge or pass through.

### 5. Pricing Tipping Point Chart

**What it does:** Pre-computes 5 price scenarios (Baseline to Extreme +75%) and shows how many products shift from "absorb the cost" to "must reprice."

**How to read the chart:** Stacked bars per scenario. Green = ABSORB (hold prices, margin buffer is enough). Orange = PARTIAL PASS-THROUGH (pass 60% of cost increase to price). Red = FULL REPRICE (pass 85% to price). As scenarios get worse, more products flip from green to red.

**Business value:** This is the "at what point do we raise prices?" answer. The chart shows that at +30% raw material inflation, 98 of 100 products need some price action. The What-If simulator lets you test custom scenarios live.

---

## What-If Simulator

The sidebar has three controls:
- **Barley price change %** -- simulate commodity price shocks
- **Hops price change %** -- simulate commodity price shocks
- **Simulate DC offline** -- pick a DC and set how many weeks it's down

For the Supply Chain tab, the DC offline simulator shows a stockout countdown. For the Sales tab, the price sliders recompute margins and pricing recommendations in real time.

**Demo tip:** During the live webinar, drag barley to +50% and watch products flip from green (ABSORB) to red (FULL REPRICE). Then select "DC-ATL - Atlanta" offline for 8 weeks and show the stockout risk.

---

## Repo Structure

```
SupplyChainWebinar/
  setup.sh                    # One-command setup script
  streamlit_app.py            # Streamlit dashboard (deployed to SiS)
  data/                       # 14 CSV files (~4.8 MB total)
  scripts/
    01_setup_database.sql     # DB, schemas, table DDLs
    02_load_data.sql          # Stage + COPY INTO
    03_create_views.sql       # ML input views
    04_create_ml_models.sql   # Snowflake ML model creation
    05_deploy_streamlit.sql   # Streamlit app deployment + grants
  .gitignore
  README.md
```

## Teardown

To remove everything:

```sql
DROP DATABASE IF EXISTS BEERCOMPANYDEMO;
```
