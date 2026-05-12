"""ui/cycle_time.py — Cycle Time tab."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.metrics import cycle_time_stats, cycle_time_by_type, cycle_time_series
from config.schema import AppConfig
from ui.charts import cycle_time_scatter


def render(df: pd.DataFrame, config: AppConfig) -> None:
    st.header("Cycle Time")

    with st.expander("ℹ️ What this tells you", expanded=False):
        st.markdown(
            "Cycle time measures how long work takes from creation to resolution "
            "(calendar days). The scatterplot shows individual items; percentile lines "
            "let you make probabilistic statements: '85% of stories are done within X days.' "
            "Lower and more consistent cycle times indicate healthier flow. "
            "\n\n"
            "**Note:** Cycle times are calculated in *calendar* days (Resolved − Created). "
            "This is a lower bound — items may have been waiting in a backlog before work "
            "started. Per-state residency analysis is available in Phase 2."
        )

    if df.empty:
        st.info("No data loaded.")
        return

    # Controls
    col1, col2 = st.columns([3, 1])
    with col2:
        group_by = st.selectbox(
            "Colour by", ["type", "squad", "status"], index=0,
            key="ct_group_by",
        )
        percentiles = st.multiselect(
            "Percentile lines",
            options=[50, 70, 85, 95],
            default=[50, 85, 95],
            key="ct_percentiles",
        )

    with col1:
        fig = cycle_time_scatter(df, percentiles=percentiles, group_col=group_by)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Summary statistics table
    st.subheader("Summary statistics by type")
    stats_by_type = cycle_time_by_type(df)
    if stats_by_type:
        rows = []
        for itype, s in stats_by_type.items():
            if s.count > 0:
                rows.append({
                    "Type": itype,
                    "Count": s.count,
                    "Median (d)": round(s.p50, 1),
                    "70th (d)": round(s.p70, 1),
                    "85th (d)": round(s.p85, 1),
                    "95th (d)": round(s.p95, 1),
                    "Mean (d)": round(s.mean, 1),
                    "Min (d)": round(s.min, 1),
                    "Max (d)": round(s.max, 1),
                })
        if rows:
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

    # Raw items table (expandable)
    with st.expander("📋 View all items with cycle time"):
        ct_col = cycle_time_series(df).rename("Cycle time (days)")
        display = df[["key", "title", "type", "squad", "status", "created", "resolved"]].copy()
        display["cycle_time_days"] = ct_col.round(1)
        display = display[display["cycle_time_days"].notna()].sort_values(
            "cycle_time_days", ascending=False
        )
        display.columns = ["Key", "Title", "Type", "Squad", "Status",
                           "Created", "Resolved", "Cycle time (days)"]
        st.dataframe(display, use_container_width=True, hide_index=True)
