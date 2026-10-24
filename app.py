"""
Filling Up at the Right Price? — Data storytelling on fuel prices in France
Source: data.gouv.fr — "Prix des carburants en France – Flux instantané – v2"
Run: streamlit run app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SOURCE_URL = "https://www.data.gouv.fr/fr/datasets/6407d088d4e23dc662022e2c"

# --- Palette (colour-blind validated, see README) ------------------------------
BLUE, ORANGE = "#2a78d6", "#eb6834"
DIVERGING = [[0.0, "#1c5cab"], [0.25, "#86b6ef"], [0.5, "#e6e5e1"], [0.75, "#ee9a99"], [1.0, "#b8302f"]]
GRID = "rgba(128,128,128,0.18)"
FUEL_LABELS = {
    "Gazole": "Diesel (Gazole)", "E10": "Unleaded E10", "SP98": "Unleaded 98 (SP98)",
    "SP95": "Unleaded 95 (SP95)", "E85": "E85 (bioethanol)", "GPLc": "LPG (GPLc)",
}
TANK_L = 50  # reference tank volume (litres)
ALL_FRANCE = "Mainland France"

st.set_page_config(page_title="Filling Up at the Right Price?", page_icon="⛽", layout="wide")


# =============================================================================
# Data
# =============================================================================
@st.cache_data(show_spinner="Loading data…")
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if not (DATA / "prices_long.csv").exists():
        from prepare_data import main as prepare  # rebuild from the raw CSV
        prepare()
    stations = pd.read_csv(DATA / "stations_clean.csv", dtype={"department_code": str, "postcode": str})
    prices = pd.read_csv(DATA / "prices_long.csv", dtype={"department_code": str})
    report = json.loads((DATA / "quality_report.json").read_text(encoding="utf-8"))
    return stations, prices, report


@st.cache_data
def dept_stats(prices: pd.DataFrame, fuel: str) -> pd.DataFrame:
    """Price distribution per department for one fuel."""
    p = prices[prices.fuel == fuel]
    g = p.groupby(["department_code", "department", "region"]).price
    out = g.agg(median="median", p10=lambda s: s.quantile(0.10), p90=lambda s: s.quantile(0.90),
                min="min", max="max", n="count").reset_index()
    out["spread_p10_p90"] = out.p90 - out.p10
    return out[out.n >= 10]  # departments with too few stations are excluded (noise)


def style(fig: go.Figure, height: int = 420) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(size=13), hoverlabel=dict(font_size=13))
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def eur(x: float, d: int = 2) -> str:
    sign = "−" if x < 0 else ""
    return f"{sign}€{abs(x):,.{d}f}"


stations, prices, report = load_data()
snapshot = pd.Timestamp(report["snapshot_utc"]).tz_convert("Europe/Paris")

# =============================================================================
# Sidebar — filters
# =============================================================================
with st.sidebar:
    st.header("⛽ Settings")
    fuels_available = [f for f in FUEL_LABELS if f in prices.fuel.unique()]
    fuel = st.selectbox("Fuel", fuels_available, index=0, format_func=lambda f: FUEL_LABELS[f])
    regions = sorted(stations.region.dropna().unique())
    region = st.selectbox("Zoom on a region", [ALL_FRANCE] + regions)
    st.caption(f"Snapshot of **{snapshot:%d %b %Y, %H:%M}** (Paris time) · {report['n_stations_final']:,} stations")
    st.divider()
    st.markdown(f"Source: [data.gouv.fr – Fuel prices in France]({SOURCE_URL})")

pf = prices[prices.fuel == fuel]
pf_zone = pf if region == ALL_FRANCE else pf[pf.region == region]
nat_median = pf.price.median()
zone_label = "France" if region == ALL_FRANCE else region

# =============================================================================
# 1. HOOK
# =============================================================================
st.title("Filling Up at the Right Price?")
st.markdown("#### Where you fill up matters more than where you live.")

diesel = prices[prices.fuel == "Gazole"].price
c1, c2, c3, c4 = st.columns(4)
c1.metric("Diesel — median price", eur(diesel.median(), 3) + "/L")
c2.metric(f"One {TANK_L} L tank of diesel", eur(diesel.median() * TANK_L, 0))
c3.metric("Stations with a shortage", f"{report['pct_stations_shortage']:.0f}%",
          help="At least one fuel temporarily unavailable at extraction time.")
spread_dept = dept_stats(prices, "Gazole").spread_p10_p90.median()
c4.metric("Typical gap within a department", eur(spread_dept * TANK_L, 0) + " / tank",
          help="Median, across departments, of the gap between the cheapest 10% and the most expensive 10% "
               "of stations (diesel), for a 50 L tank.")

st.info(
    f"With diesel at around **{eur(diesel.median(), 2)}/L**, a full tank costs more than "
    f"**{eur(diesel.median() * TANK_L, 0)}**. Almost **one station in four** is out of at least one fuel. "
    f"The question is not only *\"how much does fuel cost?\"* but **\"how much can I save by choosing my station?\"**"
)

# =============================================================================
# 2. CONTEXT
# =============================================================================
with st.expander("📋 Context: where do these numbers come from?", expanded=False):
    st.markdown(f"""
- **Source:** official feed from the French Ministry of the Economy, published on data.gouv.fr. Fuel stations are
  legally required to report their prices and shortages.
- **Nature:** a **snapshot** (taken on {snapshot:%d %b %Y}), not a time series. Each row is one station,
  with the latest known price for each fuel.
- **Cleaning:** prices not updated for more than 30 days removed (stale), prices outside plausibility bounds
  removed, coordinates converted (the file stores them × 100,000).
- **Scope:** {report['n_stations_final']:,} stations, {report['n_prices_final']:,} valid prices. Departments with
  fewer than 10 stations for a given fuel are excluded from rankings.
""")
    q = pd.DataFrame(report["prices"]).T.rename(index=FUEL_LABELS, columns={
        "raw_non_null": "Raw prices", "implausible_removed": "Removed (implausible)",
        "stale_removed": "Removed (stale > 30 days)", "kept": "Kept"})
    st.dataframe(q, width="stretch")

# =============================================================================
# 3. INSIGHT 1 — The map
# =============================================================================
st.header(f"1. Price map: {FUEL_LABELS[fuel]}")
st.markdown(
    f"Each dot is a station. **Blue = cheaper** than the national median ({eur(nat_median, 3)}/L), "
    "**red = more expensive**. Regional trends exist, but look above all at the **mix of colours "
    "inside every area**."
)

map_df = pf_zone.dropna(subset=["lat", "lon"]).copy()
map_df["gap_cts"] = (map_df.price - nat_median) * 100
lim = max(5.0, float(map_df.gap_cts.abs().quantile(0.95)))
map_mode = st.radio("Map background", ["Simple (fast)", "Detailed (OpenStreetMap)"], horizontal=True,
                    help="The detailed background shows streets (requires WebGL).")
common = dict(color="gap_cts", range_color=(-lim, lim), color_continuous_scale=DIVERGING, hover_name="city",
              hover_data={"price": ":.3f", "department": True, "road_type": True, "gap_cts": ":+.1f",
                          "lat": False, "lon": False},
              labels={"gap_cts": "Gap (cents/L)", "price": "Price €/L", "department": "Department",
                      "road_type": "Type"}, height=620)
if map_mode.startswith("Simple"):
    fig_map = px.scatter_geo(map_df, lat="lat", lon="lon", **common)
    fig_map.update_geos(fitbounds="locations", showcountries=True, countrycolor="rgba(128,128,128,0.5)",
                        showland=True, landcolor="rgba(128,128,128,0.06)", showocean=False, showlakes=False,
                        showframe=False, projection_type="mercator", bgcolor="rgba(0,0,0,0)",
                        showsubunits=True, resolution=50)
    fig_map.update_traces(marker=dict(size=4.5, opacity=0.85, line=dict(width=0)))
else:
    HAS_MAP = hasattr(px, "scatter_map")  # plotly >= 5.24 (MapLibre); otherwise legacy scatter_mapbox
    map_fn = px.scatter_map if HAS_MAP else px.scatter_mapbox
    fig_map = map_fn(map_df, lat="lat", lon="lon", zoom=4.6 if region == ALL_FRANCE else 6.5, **common)
    fig_map.update_traces(marker=dict(size=6, opacity=0.85))
    fig_map.update_layout(**({"map_style": "carto-positron"} if HAS_MAP else {"mapbox_style": "carto-positron"}))
fig_map.update_layout(margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      coloraxis_colorbar=dict(title="cents/L<br>vs median"))
st.plotly_chart(fig_map, width="stretch")

# =============================================================================
# 4. INSIGHT 2 — Rankings and within-department spread
# =============================================================================
st.header("2. Between departments: a few cents. Within a department: much more.")

ds = dept_stats(prices, fuel)
ds_zone = ds if region == ALL_FRANCE else ds[ds.region == region]
# Like-for-like comparison: P10–P90 spread of department medians (between departments)
# vs median P10–P90 spread between stations of the same department (within a department).
inter = ds["median"].quantile(0.90) - ds["median"].quantile(0.10)
inter_extreme = ds["median"].max() - ds["median"].min()
intra = ds.spread_p10_p90.median()

col_a, col_b = st.columns(2)
col_a.metric("Typical gap between departments", f"{inter * 100:.0f} cents/L",
             help="Gap between the 10th and 90th percentile of department median prices. "
                  f"Between the two most extreme departments: {inter_extreme * 100:.0f} cents/L.")
col_b.metric("Typical gap between stations of the same department", f"{intra * 100:.0f} cents/L",
             help="Median of the P10–P90 spreads computed within each department.")

n_show = st.slider("Number of departments shown (top / bottom)", 5, 15, 10)
ranked = ds_zone.sort_values("median")
subset = pd.concat([ranked.head(n_show), ranked.tail(n_show)]).drop_duplicates("department_code")
subset = subset.sort_values("median")
subset["label"] = subset.department + " (" + subset.department_code + ")"

fig_rank = go.Figure()
fig_rank.add_trace(go.Scatter(  # P10–P90 bar: the within-department spread
    x=pd.concat([subset.p10, subset.p90, pd.Series([None] * len(subset))]).values.reshape(3, -1).T.ravel(),
    y=np.repeat(subset.label.values, 3),
    mode="lines", line=dict(color="rgba(42,120,214,0.35)", width=8), name="10% → 90% of stations",
    hoverinfo="skip"))
fig_rank.add_trace(go.Scatter(
    x=subset["median"], y=subset.label, mode="markers",
    marker=dict(color=BLUE, size=10, line=dict(color="white", width=2)),
    name="Median price", customdata=subset[["p10", "p90", "n"]],
    hovertemplate="<b>%{y}</b><br>Median: €%{x:.3f}/L<br>P10: €%{customdata[0]:.3f} · P90: €%{customdata[1]:.3f}"
                  "<br>%{customdata[2]} stations<extra></extra>"))
fig_rank.add_vline(x=nat_median, line_dash="dot", line_color="gray",
                   annotation_text=f"France median €{nat_median:.3f}", annotation_position="bottom right")
pad = 0.02
fig_rank.update_layout(xaxis_title="€/L", legend=dict(orientation="h", y=1.04, x=0, yanchor="bottom"),
                       xaxis_range=[subset.p10.min() - pad, subset.p90.max() + pad])
st.plotly_chart(style(fig_rank, height=max(420, 26 * len(subset))), width="stretch")

st.success(
    f"**Insight:** for {FUEL_LABELS[fuel]}, median prices typically vary by **{inter * 100:.0f} cents/L** from "
    f"one department to another, but by **{intra * 100:.0f} cents/L** between stations of the same department — "
    f"**{intra / inter:.1f} times more**. "
    + (f"The local gap even matches or exceeds the gap between the two most extreme departments "
       f"({inter_extreme * 100:.0f} cents/L). " if intra >= 0.95 * inter_extreme else
       f"Only the two most extreme departments differ more ({inter_extreme * 100:.0f} cents/L). ")
    + "**Choosing your station matters more than where you live.**"
)

with st.expander("See the full department table"):
    st.dataframe(
        ds_zone.sort_values("median").rename(columns={
            "department_code": "Code", "department": "Department", "region": "Region", "median": "Median €/L",
            "p10": "P10", "p90": "P90", "min": "Min", "max": "Max", "n": "Stations",
            "spread_p10_p90": "P10–P90 spread"}),
        width="stretch", hide_index=True)

# =============================================================================
# 5. INSIGHT 3 — The motorway premium
# =============================================================================
st.header("3. The \"motorway tax\"")
hw = pf_zone.groupby("road_type").price.agg(["median", "count"]).reindex(["Road", "Motorway"]).dropna()
if {"Road", "Motorway"} <= set(hw.index):
    premium = hw.loc["Motorway", "median"] - hw.loc["Road", "median"]
    left, right = st.columns([2, 1])
    with left:
        box_df = pf_zone[pf_zone.road_type.isin(["Road", "Motorway"])]
        fig_box = px.box(box_df, x="price", y="road_type", color="road_type", points=False,
                         color_discrete_map={"Road": BLUE, "Motorway": ORANGE},
                         category_orders={"road_type": ["Road", "Motorway"]},
                         labels={"price": "€/L", "road_type": ""})
        fig_box.update_layout(showlegend=False)
        st.plotly_chart(style(fig_box, 300), width="stretch")
    with right:
        st.metric("Median extra cost on motorways", f"+{premium * 100:.0f} cents/L")
        st.metric(f"That is, on a {TANK_L} L tank", f"+{eur(premium * TANK_L, 0)}")
        st.caption(f"{int(hw.loc['Motorway', 'count'])} motorway stations vs "
                   f"{int(hw.loc['Road', 'count'])} on regular roads ({zone_label}).")
    st.markdown("Motorway stations are few (≈ 4% of the network) but **consistently more expensive**: "
                "filling up before getting on the motorway remains the most profitable habit.")
else:
    st.warning("Not enough motorway stations in this area to compare.")

# =============================================================================
# 6. INSIGHT 4 — Shortages
# =============================================================================
st.header("4. Shortages: a network under strain")
st_zone = stations if region == ALL_FRANCE else stations[stations.region == region]
shortage_fuel = pd.DataFrame({
    "fuel": [FUEL_LABELS[f] for f in FUEL_LABELS],
    "pct": [st_zone[f"shortage_{f}"].mean() * 100 for f in FUEL_LABELS]}).sort_values("pct")
shortage_reg = (stations.groupby("region").shortage_any.mean() * 100).sort_values().reset_index()
shortage_reg["colour"] = np.where(shortage_reg.region == region, ORANGE, BLUE)

r1, r2 = st.columns(2)
with r1:
    fig_sf = px.bar(shortage_fuel, x="pct", y="fuel", orientation="h",
                    text=shortage_fuel.pct.map(lambda v: f"{v:.1f}%"),
                    labels={"pct": "% of stations with a shortage", "fuel": ""}, title=f"By fuel ({zone_label})")
    fig_sf.update_traces(marker_color=BLUE, textposition="outside", cliponaxis=False,
                         hovertemplate="%{y}: %{x:.1f}%<extra></extra>")
    fig_sf.update_xaxes(range=[0, shortage_fuel.pct.max() * 1.25])
    st.plotly_chart(style(fig_sf, 340), width="stretch")
with r2:
    fig_sr = px.bar(shortage_reg, x="shortage_any", y="region", orientation="h",
                    labels={"shortage_any": "% of stations with at least one shortage", "region": ""},
                    title="By region (all fuels)")
    fig_sr.update_traces(marker_color=shortage_reg.colour, hovertemplate="%{y}: %{x:.1f}%<extra></extra>")
    st.plotly_chart(style(fig_sr, 340), width="stretch")

top_reg = shortage_reg.iloc[-1]
top_fuels = shortage_fuel.sort_values("pct", ascending=False).fuel.head(2).tolist()
st.markdown(
    f"Shortages hit **{top_fuels[0]}** first, then **{top_fuels[1]}**. They are more frequent in dense regions: "
    f"**{top_reg.region}** is the most affected ({top_reg.shortage_any:.0f}% of stations). "
    "For drivers, potential savings come with a risk: the cheapest station does not always have your fuel."
)

# =============================================================================
# 7. WHAT-IF — Simulator
# =============================================================================
st.header("5. What about you? The simulator")
st.markdown("Adjust your habits: the app computes what **choosing your station** changes over a year.")

dept_opts = ds.sort_values("department")
s1, s2, s3 = st.columns(3)
with s1:
    km = st.slider("Kilometres per year", 2_000, 40_000, 12_000, step=1_000)
    consumption = st.slider("Consumption (L/100 km)", 3.0, 12.0, 6.0, step=0.5)
with s2:
    dept_list = dept_opts.department.tolist()
    dept_choice = st.selectbox("Your department", dept_list,
                               index=dept_list.index("Paris") if "Paris" in dept_list else 0)
    detour = st.slider("Round-trip detour to reach a cheaper station (km)", 0, 30, 6)

row = ds[ds.department == dept_choice].iloc[0]
litres = km * consumption / 100
cost_cheap, cost_med, cost_exp = litres * row.p10, litres * row["median"], litres * row.p90
fills = litres / TANK_L
detour_cost = fills * detour * consumption / 100 * row.p10
net_saving = cost_med - cost_cheap - detour_cost

with s3:
    st.metric("Litres used per year", f"{litres:,.0f} L")
    st.metric("Net saving per year vs median station", eur(net_saving, 0),
              help="By using the cheapest 10% of stations in your department, detour cost deducted.")
    st.caption(f"Detour cost: {eur(detour_cost, 0)} / year")

budget_cheap = cost_cheap + detour_cost
sim = pd.DataFrame({
    "Scenario": ["Median station", "Most expensive 10%"],
    "Extra": [cost_med - budget_cheap, cost_exp - budget_cheap]})
fig_sim = px.bar(sim, x="Extra", y="Scenario", orientation="h", labels={"Scenario": ""},
                 text=sim["Extra"].map(lambda v: ("+" if v >= 0 else "") + eur(v, 0)),
                 title="How much more you pay per year compared with the cheapest stations (detour included)")
fig_sim.update_traces(marker_color=[BLUE, ORANGE], textposition="outside", cliponaxis=False,
                      hovertemplate="%{y}: +€%{x:,.0f} / year<extra></extra>")
fig_sim.update_xaxes(range=[min(0, sim.Extra.min() * 1.2), max(1, sim.Extra.max() * 1.2)],
                     title=f"€ / year — {FUEL_LABELS[fuel]}, {dept_choice}")
st.plotly_chart(style(fig_sim, 240), width="stretch")
st.caption(f"Annual budget: {eur(budget_cheap, 0)} (cheapest + detours) · {eur(cost_med, 0)} (median) · "
           f"{eur(cost_exp, 0)} (most expensive).")

breakeven_km = ((row["median"] - row.p10) * TANK_L / (consumption / 100 * row.p10)
                if row["median"] > row.p10 else 0)
st.caption(
    f"Is the detour worth it? With a {TANK_L} L tank, a detour pays off as long as it is shorter than "
    f"**{breakeven_km:.0f} km round trip**. Assumptions: department P10 / median / P90 prices for the selected "
    f"fuel, one detour per fill-up."
)

if fuel in ("SP98", "E10", "SP95") and "E85" in prices.fuel.unique():
    with st.expander("🔁 What if I switched to E85?"):
        e85 = dept_stats(prices, "E85")
        e85_row = e85[e85.department == dept_choice]
        e85_price = e85_row["median"].iloc[0] if len(e85_row) else prices[prices.fuel == "E85"].price.median()
        overuse = st.slider("Extra consumption with E85 (%)", 10, 40, 25,
                            help="E85 contains less energy per litre: +20 to +30% is the usual estimate.")
        kit = st.number_input("Conversion kit cost (€)", 0, 3000, 1000, step=100)
        cost_e85 = litres * (1 + overuse / 100) * e85_price
        gain = cost_med - cost_e85
        e1, e2 = st.columns(2)
        e1.metric("Annual saving with E85 vs current fuel", eur(gain, 0))
        e2.metric("Kit paid back in", f"{kit / gain * 12:.0f} months" if gain > 0 else "never")
        st.caption("Adjustable assumptions. E85 price: department median (or national median if < 10 stations). "
                   "Not every car is compatible.")

# =============================================================================
# 8. IMPLICATIONS & LIMITATIONS
# =============================================================================
st.header("Key takeaways")
st.markdown(f"""
1. **Price depends mostly on the station.** The typical gap within a department (~{intra * 100:.0f} cents/L) is
   {intra / inter:.0f} times the gap between departments (~{inter * 100:.0f} cents/L). Comparing stations before
   driving is the first lever for saving money.
2. **Motorways are expensive.** Filling up before getting on the motorway avoids an extra cost of about 10 cents/L.
3. **The network is under strain.** Almost one station in four has a partial shortage: the cheapest station is only
   useful if it actually has fuel.

**Next steps:** combine with the daily history (data.gouv.fr also publishes yearly archives) to measure trends over
time, add station brands (missing from this feed), and link to median income per municipality (INSEE) to measure the
fuel burden on households.
""")

with st.expander("⚠️ Limitations and assumptions"):
    st.markdown(f"""
- **Snapshot:** prices change every day; conclusions hold for {snapshot:%d %b %Y}.
- **Self-reported data:** prices are entered by stations. Stale (> 30 days) and implausible prices are removed.
- **No brand** in this feed: supermarkets cannot be compared with oil companies.
- **Simulator:** deliberately simple model (prices constant over the year, one detour per fill-up, {TANK_L} L tank).
- **Shortages:** only *temporary* shortages are counted; a fuel that is never sold is not a shortage.
""")

st.caption(f"Data: [data.gouv.fr]({SOURCE_URL}) · Licence Ouverte Etalab 2.0 · StApp26 project — EFREI BIA")
