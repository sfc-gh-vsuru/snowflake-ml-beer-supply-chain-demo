import streamlit as st
import pandas as pd
import altair as alt
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="Beer Co. Supply Chain & Pricing Intelligence", layout="wide")

DB = "BEERCOMPANYDEMO"
session = get_active_session()


@st.cache_data(ttl=600)
def run_query(sql):
    return session.sql(sql).to_pandas()


# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title(":beer: Beer Co. Intelligence")
    persona = st.radio(
        "Select your view",
        ["Supply Chain Risk Manager", "Beer Sales Head"],
        index=0,
    )
    st.divider()
    st.subheader("What-If Simulator")
    barley_shock = st.slider("Barley price change %", -20, 80, 0, 5)
    hops_shock = st.slider("Hops price change %", -20, 80, 0, 5)
    dc_options = run_query(f"""
        SELECT LOCATION_ID || ' - ' || CITY AS LABEL, LOCATION_ID AS DC_ID
        FROM {DB}.ANALYTICS.DISTRIBUTION_NETWORK WHERE LOCATION_TYPE = 'DC' ORDER BY CITY
    """)
    dc_choices = ["None"] + dc_options["LABEL"].tolist()
    disruption_dc = st.selectbox("Simulate DC offline", dc_choices)
    disruption_weeks = st.slider("Disruption duration (weeks)", 1, 12, 4)
    st.divider()
    st.caption("Powered by Snowflake ML | Data from Coalesce")


# ═══════════════════════════════════════════════════════════════════════════
# SUPPLY CHAIN RISK MANAGER
# ═══════════════════════════════════════════════════════════════════════════
if persona == "Supply Chain Risk Manager":
    st.header("Supply Chain Risk Dashboard")

    # ── KPI row ──
    inv = run_query(f"""
        SELECT DC_ID, DC_NAME, ON_HAND_UNITS, DAYS_OF_SUPPLY, RISK_STATUS,
               AVG_LEAD_DAYS, AVG_SUPPLY_DISRUPTION
        FROM {DB}.ANALYTICS.WEEKLY_INVENTORY
        WHERE WEEK_START_DATE = (SELECT MAX(WEEK_START_DATE) FROM {DB}.ANALYTICS.WEEKLY_INVENTORY)
    """)
    total_stock = int(inv["ON_HAND_UNITS"].sum())
    avg_dos = round(float(inv["DAYS_OF_SUPPLY"].mean()), 1)
    avg_lead = round(float(inv["AVG_LEAD_DAYS"].mean()), 1)
    risk_counts = inv["RISK_STATUS"].value_counts()
    critical = int(risk_counts.get("CRITICAL", 0)) + int(risk_counts.get("AT_RISK", 0))

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Inventory", f"{total_stock:,}")
    k2.metric("Avg Days of Supply", f"{avg_dos}")
    k3.metric("Avg Lead Time (days)", f"{avg_lead}")
    k4.metric("DCs At Risk/Critical", f"{critical} / {len(inv)}")

    # ── Row 1: Network Map + Event Timeline ──
    col_map, col_timeline = st.columns([2, 3])

    with col_map:
        st.subheader("Distribution Network")
        network = run_query(f"""
            SELECT n.LOCATION_ID, n.LOCATION_NAME, n.LOCATION_TYPE, n.CITY, n.STATE,
                   n.LATITUDE, n.LONGITUDE,
                   COALESCE(i.RISK_STATUS, 'N/A') AS RISK_STATUS
            FROM {DB}.ANALYTICS.DISTRIBUTION_NETWORK n
            LEFT JOIN (
                SELECT DC_ID, RISK_STATUS
                FROM {DB}.ANALYTICS.WEEKLY_INVENTORY
                WHERE WEEK_START_DATE = (SELECT MAX(WEEK_START_DATE) FROM {DB}.ANALYTICS.WEEKLY_INVENTORY)
            ) i ON i.DC_ID = n.LOCATION_ID
        """)

        # Basic st.map for SiS compatibility (lat/lon only)
        map_df = network[["LATITUDE", "LONGITUDE"]].copy()
        map_df.columns = ["latitude", "longitude"]
        st.map(map_df, zoom=3)

        # Show network table with risk status for DCs
        dc_status = network[network["LOCATION_TYPE"] == "DC"][
            ["LOCATION_ID", "CITY", "STATE", "RISK_STATUS"]
        ].copy()
        dc_status["STATUS"] = dc_status["RISK_STATUS"].map({
            "CRITICAL": "🔴 CRITICAL",
            "AT_RISK": "🟡 AT RISK",
            "ELEVATED": "🟠 ELEVATED",
            "NORMAL": "🟢 NORMAL",
        })
        st.dataframe(
            dc_status[["LOCATION_ID", "CITY", "STATUS"]].reset_index(drop=True),
            use_container_width=True,
        )
        st.caption(
            "Map shows: Breweries, Suppliers, DCs, and Distributors across the US network"
        )

    with col_timeline:
        st.subheader("Disruption Timeline & Inventory Impact")
        events = run_query(f"""
            SELECT EVENT_NAME, EVENT_CATEGORY, START_DATE, END_DATE, SEVERITY
            FROM {DB}.ANALYTICS.GEOPOLITICAL_EVENTS ORDER BY START_DATE
        """)
        inv_ts = run_query(f"""
            SELECT WEEK_START_DATE, DC_ID, ON_HAND_UNITS
            FROM {DB}.ANALYTICS.WEEKLY_INVENTORY ORDER BY WEEK_START_DATE
        """)

        base_line = (
            alt.Chart(inv_ts)
            .mark_line(strokeWidth=1.5)
            .encode(
                x=alt.X("WEEK_START_DATE:T", title=""),
                y=alt.Y("ON_HAND_UNITS:Q", title="On-Hand Units"),
                color=alt.Color("DC_ID:N", legend=alt.Legend(title="DC")),
            )
        )
        event_rects = (
            alt.Chart(events)
            .mark_rect(opacity=0.15)
            .encode(
                x="START_DATE:T",
                x2="END_DATE:T",
                color=alt.Color(
                    "EVENT_CATEGORY:N",
                    scale=alt.Scale(
                        domain=["WAR", "CONFLICT", "HURRICANE", "WINTER_STORM", "WILDFIRE",
                                "DROUGHT", "SEVERE_STORM", "TARIFF", "STRIKE"],
                        range=["#d62728", "#ff7f0e", "#e377c2", "#17becf", "#ff4500",
                               "#8b4513", "#9467bd", "#7f7f7f", "#bcbd22"],
                    ),
                    legend=alt.Legend(title="Event Type"),
                ),
            )
        )
        st.altair_chart(
            (event_rects + base_line).properties(height=350).interactive(),
            use_container_width=True,
        )

    # ── Row 2: Forecast + Anomalies ──
    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Inventory Forecast (12-Week)")
        hist = run_query(f"""
            SELECT WEEK_START_DATE AS TS, DC_ID AS SERIES,
                   ON_HAND_UNITS AS VALUE, 'Actual' AS TYPE
            FROM {DB}.ANALYTICS.WEEKLY_INVENTORY
            WHERE WEEK_START_DATE >= DATEADD(month, -6, CURRENT_DATE())
        """)
        fcst = run_query(f"SELECT * FROM {DB}.ML.INVENTORY_FORECAST")
        fcst_plot = fcst.copy()
        fcst_plot["VALUE"] = fcst_plot["FORECAST"]
        fcst_plot["TYPE"] = "Forecast"

        combined = pd.concat([
            hist[["TS", "SERIES", "VALUE", "TYPE"]],
            fcst_plot[["TS", "SERIES", "VALUE", "TYPE"]],
        ], ignore_index=True)

        line = (
            alt.Chart(combined)
            .mark_line()
            .encode(
                x=alt.X("TS:T", title=""),
                y=alt.Y("VALUE:Q", title="Inventory Units"),
                color="SERIES:N",
                strokeDash=alt.StrokeDash(
                    "TYPE:N",
                    scale=alt.Scale(domain=["Actual", "Forecast"], range=[[1, 0], [5, 5]]),
                ),
            )
        )
        band = (
            alt.Chart(fcst)
            .mark_area(opacity=0.15)
            .encode(x="TS:T", y="LOWER_BOUND:Q", y2="UPPER_BOUND:Q", color="SERIES:N")
        )
        st.altair_chart(
            (line + band).properties(height=300).interactive(), use_container_width=True
        )

    with col4:
        st.subheader("Lead Time Anomaly Detection")
        anomalies = run_query(f"""
            SELECT * FROM {DB}.ML.LEAD_TIME_ANOMALIES
            WHERE SERIES LIKE 'DC-%'
            ORDER BY TS
        """)
        if not anomalies.empty:
            anm_chart = (
                alt.Chart(anomalies)
                .mark_circle(size=80)
                .encode(
                    x=alt.X("TS:T", title=""),
                    y=alt.Y("Y:Q", title="Avg Lead Days"),
                    color=alt.condition(
                        alt.datum.IS_ANOMALY == True,
                        alt.value("#d62728"),
                        alt.value("#1f77b4"),
                    ),
                    size=alt.condition(
                        alt.datum.IS_ANOMALY == True, alt.value(200), alt.value(60)
                    ),
                    tooltip=["SERIES", "TS:T", "Y", "IS_ANOMALY"],
                )
            )
            band_anm = (
                alt.Chart(anomalies)
                .mark_area(opacity=0.08, color="gray")
                .encode(x="TS:T", y="LOWER_BOUND:Q", y2="UPPER_BOUND:Q")
            )
            st.altair_chart(
                (band_anm + anm_chart).properties(height=300).interactive(),
                use_container_width=True,
            )
            n_anomalies = int(anomalies["IS_ANOMALY"].sum())
            if n_anomalies > 0:
                anom_dcs = anomalies[anomalies["IS_ANOMALY"] == True]["SERIES"].unique()
                st.error(
                    f"**{n_anomalies} anomalies detected** at {', '.join(anom_dcs)} "
                    "-- lead times exceeded normal bounds."
                )
        else:
            st.info("No anomaly data for DC-level routes in test window.")

    # ── What-If Simulator: DC Offline ──
    if disruption_dc != "None":
        st.divider()
        st.subheader("Simulated Disruption Impact")
        dc_code = disruption_dc.split(" - ")[0]
        sim_inv = run_query(f"""
            SELECT DC_ID, DC_NAME, ON_HAND_UNITS, WEEKLY_DEMAND_UNITS, DAYS_OF_SUPPLY
            FROM {DB}.ANALYTICS.WEEKLY_INVENTORY
            WHERE WEEK_START_DATE = (SELECT MAX(WEEK_START_DATE) FROM {DB}.ANALYTICS.WEEKLY_INVENTORY)
              AND DC_ID = '{dc_code}'
        """)
        if not sim_inv.empty:
            current_inv = float(sim_inv["ON_HAND_UNITS"].iloc[0])
            weekly_demand = float(sim_inv["WEEKLY_DEMAND_UNITS"].iloc[0])
            weeks_until_stockout = round(current_inv / max(weekly_demand, 1), 1)
            remaining_after = max(0, current_inv - weekly_demand * disruption_weeks)

            s1, s2, s3 = st.columns(3)
            s1.metric(f"{dc_code} Current Stock", f"{current_inv:,.0f}")
            s2.metric("Weeks Until Stockout", f"{weeks_until_stockout}", f"-{disruption_weeks} week disruption")
            s3.metric(f"Stock After {disruption_weeks}wk", f"{remaining_after:,.0f}", f"{remaining_after - current_inv:,.0f}")

            if weeks_until_stockout <= disruption_weeks:
                st.error(
                    f"**STOCKOUT RISK**: {dc_code} will exhaust inventory in "
                    f"~{weeks_until_stockout} weeks. Recommend emergency rerouting from adjacent DCs."
                )
            else:
                st.success(
                    f"{dc_code} can sustain {disruption_weeks} weeks offline "
                    f"with {remaining_after:,.0f} units remaining."
                )


# ═══════════════════════════════════════════════════════════════════════════
# BEER SALES HEAD
# ═══════════════════════════════════════════════════════════════════════════
else:
    st.header("Pricing & Margin Intelligence")

    # ── KPI row ──
    margin_summary = run_query(f"""
        SELECT ROUND(AVG(AVG_MARGIN_PCT), 1) AS AVG_MARGIN,
               ROUND(SUM(TOTAL_REVENUE), 0) AS TOTAL_REV,
               ROUND(SUM(TOTAL_GROSS_PROFIT), 0) AS TOTAL_PROFIT,
               ROUND(SUM(TOTAL_UNITS), 0) AS TOTAL_UNITS
        FROM {DB}.ANALYTICS.WEEKLY_MARGIN_ANALYSIS
    """)
    ms = margin_summary.iloc[0]
    latest_prices = run_query(f"""
        SELECT MATERIAL, SPOT_PRICE FROM {DB}.ANALYTICS.RAW_MATERIAL_PRICES
        WHERE WEEK_START_DATE = (SELECT MAX(WEEK_START_DATE) FROM {DB}.ANALYTICS.RAW_MATERIAL_PRICES)
    """)
    barley_now = float(latest_prices[latest_prices["MATERIAL"] == "BARLEY"]["SPOT_PRICE"].iloc[0])
    hops_now = float(latest_prices[latest_prices["MATERIAL"] == "HOPS"]["SPOT_PRICE"].iloc[0])

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("2-Year Revenue", f"${ms['TOTAL_REV']:,.0f}")
    k2.metric("Gross Profit", f"${ms['TOTAL_PROFIT']:,.0f}")
    k3.metric("Avg Margin %", f"{ms['AVG_MARGIN']}%")
    k4.metric("Barley ($/bu)", f"${barley_now:.2f}")
    k5.metric("Hops ($/lb)", f"${hops_now:.2f}")

    # ── Row 1: Price Trends + Forecast ──
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Raw Material Price Trends")
        prices = run_query(f"""
            SELECT WEEK_START_DATE, MATERIAL, SPOT_PRICE, BASELINE_PRICE
            FROM {DB}.ANALYTICS.RAW_MATERIAL_PRICES ORDER BY MATERIAL, WEEK_START_DATE
        """)
        price_line = (
            alt.Chart(prices)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X("WEEK_START_DATE:T", title=""),
                y=alt.Y("SPOT_PRICE:Q", title="Price", scale=alt.Scale(zero=False)),
                color="MATERIAL:N",
            )
        )
        baseline = (
            alt.Chart(prices)
            .mark_line(strokeDash=[5, 5], opacity=0.4)
            .encode(x="WEEK_START_DATE:T", y="BASELINE_PRICE:Q", color="MATERIAL:N")
        )
        st.altair_chart(
            (baseline + price_line).properties(height=300).interactive(),
            use_container_width=True,
        )

    with col2:
        st.subheader("Price Forecast (12-Week)")
        price_hist = run_query(f"""
            SELECT WEEK_START_DATE AS TS, MATERIAL AS SERIES, SPOT_PRICE AS VALUE,
                   'Actual' AS TYPE
            FROM {DB}.ANALYTICS.RAW_MATERIAL_PRICES
            WHERE WEEK_START_DATE >= DATEADD(month, -6, CURRENT_DATE())
        """)
        price_fcst = run_query(f"SELECT * FROM {DB}.ML.PRICE_FORECAST")
        pf_plot = price_fcst.copy()
        pf_plot["VALUE"] = pf_plot["FORECAST"]
        pf_plot["TYPE"] = "Forecast"

        combined_p = pd.concat([
            price_hist[["TS", "SERIES", "VALUE", "TYPE"]],
            pf_plot[["TS", "SERIES", "VALUE", "TYPE"]],
        ], ignore_index=True)

        pf_line = (
            alt.Chart(combined_p)
            .mark_line()
            .encode(
                x=alt.X("TS:T", title=""),
                y=alt.Y("VALUE:Q", title="Price", scale=alt.Scale(zero=False)),
                color="SERIES:N",
                strokeDash=alt.StrokeDash(
                    "TYPE:N",
                    scale=alt.Scale(domain=["Actual", "Forecast"], range=[[1, 0], [5, 5]]),
                ),
            )
        )
        pf_band = (
            alt.Chart(price_fcst)
            .mark_area(opacity=0.15)
            .encode(x="TS:T", y="LOWER_BOUND:Q", y2="UPPER_BOUND:Q", color="SERIES:N")
        )
        st.altair_chart(
            (pf_line + pf_band).properties(height=300).interactive(),
            use_container_width=True,
        )

    # ── Row 2: Margin Trend + Top Insights ──
    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Margin Trend by Beer Style")
        margin_ts = run_query(f"""
            SELECT WEEK_START_DATE, BEER_STYLE,
                   ROUND(AVG(AVG_MARGIN_PCT), 1) AS MARGIN_PCT
            FROM {DB}.ANALYTICS.WEEKLY_MARGIN_ANALYSIS
            GROUP BY WEEK_START_DATE, BEER_STYLE ORDER BY WEEK_START_DATE
        """)
        margin_line = (
            alt.Chart(margin_ts)
            .mark_line(strokeWidth=1.5)
            .encode(
                x=alt.X("WEEK_START_DATE:T", title=""),
                y=alt.Y("MARGIN_PCT:Q", title="Margin %", scale=alt.Scale(zero=False)),
                color="BEER_STYLE:N",
            )
        )
        st.altair_chart(
            margin_line.properties(height=300).interactive(), use_container_width=True
        )

    with col4:
        st.subheader("Top Margin Drivers (ML Insights)")
        drivers = run_query(f"""
            SELECT CONTRIBUTOR,
                   ROUND(RELATIVE_CONTRIBUTION, 3) AS REL_CONTRIB,
                   ROUND(GROWTH_RATE, 3) AS GROWTH_RATE
            FROM {DB}.ML.MARGIN_DRIVER_RESULTS
            WHERE CONTRIBUTOR != '["Overall"]'
            ORDER BY ABS(CONTRIBUTION) DESC
            LIMIT 8
        """)
        drivers["DRIVER"] = drivers["CONTRIBUTOR"].apply(
            lambda x: str(x).replace("[", "").replace("]", "").replace('"', "")[:50]
        )
        driver_chart = (
            alt.Chart(drivers)
            .mark_bar()
            .encode(
                x=alt.X("REL_CONTRIB:Q", title="Relative Contribution"),
                y=alt.Y("DRIVER:N", sort="-x", title=""),
                color=alt.condition(
                    alt.datum.REL_CONTRIB > 0, alt.value("#d62728"), alt.value("#2ca02c")
                ),
            )
        )
        st.altair_chart(driver_chart.properties(height=300), use_container_width=True)

    # ── Row 3: Pricing Tipping Points ──
    st.divider()
    st.subheader("Pricing Tipping Point Analysis")

    if barley_shock == 0 and hops_shock == 0:
        tp_data = run_query(f"""
            SELECT SCENARIO_NAME, PRICING_ACTION, COUNT(*) AS CNT,
                   ROUND(AVG(SCENARIO_BARLEY_PRICE), 2) AS BARLEY_P,
                   ROUND(AVG(SCENARIO_HOPS_PRICE), 2) AS HOPS_P,
                   ROUND(AVG(MARGIN_EROSION_PCT), 1) AS AVG_EROSION,
                   ROUND(AVG(SCENARIO_MARGIN_PCT), 1) AS AVG_MARGIN
            FROM {DB}.ANALYTICS.PRICING_SCENARIO_ANALYSIS
            GROUP BY SCENARIO_NAME, PRICING_ACTION, SCENARIO_BARLEY_PRICE, SCENARIO_HOPS_PRICE
            ORDER BY BARLEY_P
        """)
        tp_chart = (
            alt.Chart(tp_data)
            .mark_bar()
            .encode(
                x=alt.X("SCENARIO_NAME:N", sort=None, title="Price Scenario"),
                y=alt.Y("CNT:Q", title="# Products"),
                color=alt.Color(
                    "PRICING_ACTION:N",
                    scale=alt.Scale(
                        domain=["ABSORB", "PARTIAL_PASS_THROUGH", "FULL_REPRICE"],
                        range=["#2ca02c", "#ff7f0e", "#d62728"],
                    ),
                    legend=alt.Legend(title="Action"),
                ),
                tooltip=["SCENARIO_NAME", "PRICING_ACTION", "CNT", "AVG_EROSION", "AVG_MARGIN"],
            )
        )
        st.altair_chart(tp_chart.properties(height=300), use_container_width=True)
        st.caption(
            "🟢 **ABSORB** = cost increase < 8%, hold prices | "
            "🟡 **PARTIAL PASS-THROUGH** = 8-18%, pass 60% to price | "
            "🔴 **FULL REPRICE** = > 18%, pass 85% to price"
        )
    else:
        st.info(f"Simulating: Barley **{barley_shock:+d}%**, Hops **{hops_shock:+d}%**")
        sim_barley = round(5.50 * (1 + barley_shock / 100), 2)
        sim_hops = round(4.20 * (1 + hops_shock / 100), 2)
        sim_results = run_query(f"""
            SELECT p.BEER_STYLE, COUNT(*) AS PRODUCTS,
                ROUND(AVG(p.BASE_RETAIL_PRICE), 2) AS AVG_PRICE,
                ROUND(AVG(p.OTHER_COGS_PER_UNIT + p.BARLEY_USAGE_PER_UNIT * 5.50 + p.HOPS_USAGE_PER_UNIT * 4.20), 2) AS BASELINE_COGS,
                ROUND(AVG(p.OTHER_COGS_PER_UNIT + p.BARLEY_USAGE_PER_UNIT * {sim_barley} + p.HOPS_USAGE_PER_UNIT * {sim_hops}), 2) AS SIM_COGS,
                ROUND(AVG((p.OTHER_COGS_PER_UNIT + p.BARLEY_USAGE_PER_UNIT * {sim_barley} + p.HOPS_USAGE_PER_UNIT * {sim_hops})
                    - (p.OTHER_COGS_PER_UNIT + p.BARLEY_USAGE_PER_UNIT * 5.50 + p.HOPS_USAGE_PER_UNIT * 4.20))
                    / NULLIF(AVG(p.OTHER_COGS_PER_UNIT + p.BARLEY_USAGE_PER_UNIT * 5.50 + p.HOPS_USAGE_PER_UNIT * 4.20), 0) * 100, 1) AS COGS_INC_PCT,
                ROUND(AVG((p.BASE_RETAIL_PRICE - (p.OTHER_COGS_PER_UNIT + p.BARLEY_USAGE_PER_UNIT * {sim_barley} + p.HOPS_USAGE_PER_UNIT * {sim_hops})) / p.BASE_RETAIL_PRICE * 100), 1) AS SIM_MARGIN_PCT
            FROM {DB}.ANALYTICS.PRODUCT_COST_STRUCTURE p
            GROUP BY p.BEER_STYLE ORDER BY COGS_INC_PCT DESC
        """)
        for _, row in sim_results.iterrows():
            cogs_inc = float(row["COGS_INC_PCT"])
            if cogs_inc <= 8:
                action, icon = "ABSORB", "🟢"
            elif cogs_inc <= 18:
                action, icon = "PARTIAL PASS-THROUGH", "🟡"
            else:
                action, icon = "FULL REPRICE", "🔴"

            c1, c2, c3, c4 = st.columns(4)
            c1.metric(f"{icon} {row['BEER_STYLE']}", f"{row['PRODUCTS']} products")
            c2.metric("COGS Increase", f"{cogs_inc:.1f}%")
            c3.metric("Simulated Margin", f"{row['SIM_MARGIN_PCT']:.1f}%")
            c4.metric("Action", action)
