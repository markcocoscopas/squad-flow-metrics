"""ui/throughput.py — Throughput tab."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.metrics import throughput_weekly, throughput_stats
from config.schema import AppConfig
from ui.charts import throughput_run_chart, throughput_histogram


def render(df: pd.DataFrame, config: AppConfig) -> None:
    st.header("Throughput")

    with st.expander("ℹ️ What this tells you", expanded=False):
        st.markdown(
            "Throughput is the number of items completed per week. It is the primary "
            "input to Monte Carlo forecasts. A stable, consistent throughput makes "
            "forecasts more reliable. High variability is normal but worth understanding: "
            "is it caused by work type, WIP, or external blockers? "
            "\n\n"
            "The histogram shows the distribution of weekly counts — the shape this "
            "distribution takes is what the Monte Carlo engine samples from."
        )

    if df.empty:
        st.info("No data loaded.")
        return

    rolling_window = st.slider("Rolling-mean window (weeks)", 2, 8, 4, key="tp_rolling")

    weekly = throughput_weekly(df)
    if weekly.empty:
        st.warning("No resolved items in the selected range — throughput cannot be calculated.")
        return

    # Run chart
    fig_run = throughput_run_chart(weekly, rolling_window=rolling_window)
    st.plotly_chart(fig_run, use_container_width=True)

    # Stats row
    tp = throughput_stats(weekly)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mean / week", f"{tp.mean_per_week:.1f}")
    c2.metric("Std dev",     f"{tp.std_per_week:.1f}")
    c3.metric("Min / week",  str(tp.min_per_week))
    c4.metric("Max / week",  str(tp.max_per_week))

    st.divider()

    # Histogram
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Distribution")
        fig_hist = throughput_histogram(weekly)
        st.plotly_chart(fig_hist, use_container_width=True)

    with col2:
        st.subheader("Weekly data")
        tbl = pd.DataFrame({
            "Week ending": weekly.index.astype(str),
            "Items": weekly.values.astype(int),
        })
        st.dataframe(tbl, use_container_width=True, hide_index=True, height=280)
