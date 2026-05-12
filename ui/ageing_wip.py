"""ui/ageing_wip.py — Ageing WIP tab."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.metrics import ageing_items, wip_over_time
from config.schema import AppConfig
from ui.charts import ageing_wip_chart, wip_over_time_chart


def render(df: pd.DataFrame, config: AppConfig) -> None:
    st.header("Ageing WIP")

    with st.expander("ℹ️ What this tells you", expanded=False):
        st.markdown(
            "Work items that have been in flight for longer than the historical 85th "
            "percentile cycle time are statistically overdue. This chart shows every "
            "in-flight item plotted by its current status on the x-axis and its age "
            "in days on the y-axis. Items above the 85th-percentile line deserve "
            "attention. Blocked items (🚫) and flagged items (⚑) are highlighted. "
            "\n\n"
            "The WIP Over Time chart shows whether your total in-flight count is "
            "growing, shrinking, or stable."
        )

    if df.empty:
        st.info("No data loaded.")
        return

    ageing = ageing_items(df, config)

    # Ageing chart
    fig = ageing_wip_chart(ageing)
    st.plotly_chart(fig, use_container_width=True)

    # Summary
    n_blocked   = sum(1 for i in ageing if i.is_blocked)
    n_over_p85  = sum(1 for i in ageing if i.age_days > i.p85_reference and i.p85_reference > 0)
    n_over_p95  = sum(1 for i in ageing if i.age_days > i.p95_reference and i.p95_reference > 0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("In-flight items",  str(len(ageing)))
    c2.metric("Blocked",          str(n_blocked))
    c3.metric("Older than p85",   str(n_over_p85))
    c4.metric("Older than p95",   str(n_over_p95))

    # WIP over time
    st.divider()
    st.subheader("WIP over time")
    wip_df = wip_over_time(df, config)
    if not wip_df.empty:
        fig2 = wip_over_time_chart(wip_df, wip_limits=config.wip_limits)
        st.plotly_chart(fig2, use_container_width=True)

    # Detail table
    if ageing:
        st.divider()
        with st.expander("📋 In-flight items detail"):
            rows = []
            for i in ageing:
                rows.append({
                    "Key": i.key,
                    "Title": i.title,
                    "Type": i.item_type,
                    "Status": i.status,
                    "Squad": i.squad,
                    "Age (d)": i.age_days,
                    "p85 ref (d)": round(i.p85_reference, 1),
                    "Blocked": "🚫" if i.is_blocked else "",
                    "Flagged": "⚑" if i.is_flagged else "",
                })
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )
