"""ui/plan_accuracy.py — Plan Accuracy & Sprint Slippage tab (bonus feature)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.plan_accuracy import (
    plan_accuracy_records,
    plan_accuracy_summary,
    sprint_slippage_summary,
)
from config.schema import AppConfig
from ui.charts import plan_accuracy_scatter


def render(df: pd.DataFrame, config: AppConfig) -> None:
    st.header("Plan Accuracy")

    with st.expander("ℹ️ What this tells you", expanded=False):
        st.markdown(
            "Plan accuracy compares the *target end date* (from Advanced Roadmaps) "
            "with the *actual resolution date*. A positive slip means the item was "
            "delivered late; negative means early.\n\n"
            "Sprint slippage counts how many items were delivered in a later sprint "
            "than planned. Both metrics help diagnose whether planning is realistic "
            "and where forecast uncertainty is highest.\n\n"
            "**Requires:** the Advanced Roadmaps CSV to be loaded alongside the "
            "snapshot CSV."
        )

    if "rm_target_end" not in df.columns:
        st.warning(
            "Advanced Roadmaps CSV not loaded. "
            "Upload it via the sidebar to enable plan accuracy metrics."
        )
        return

    records = plan_accuracy_records(df)

    if not records:
        st.info(
            "No items have both a target end date and a resolved date in the "
            "selected filters."
        )
        return

    summary = plan_accuracy_summary(records)

    # ── KPI row ───────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Items analysed",  summary.get("n_items", 0))
    c2.metric("On time (±3d)",
              f"{summary.get('n_on_time', 0)} ({summary.get('pct_on_time', 0)}%)")
    c3.metric("Late",            summary.get("n_late", 0))
    c4.metric("Early",           summary.get("n_early", 0))
    c5.metric("Median slip",
              f"{summary.get('median_slip_days', 0):+.0f} d",
              help="Positive = late on average")

    st.divider()

    # ── Scatter chart ─────────────────────────────────────────────────────────
    fig = plan_accuracy_scatter(records)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Colours: 🟢 on time (within ±3 days), 🔴 late, 🔵 early. "
        "Dashed lines show the ±3-day tolerance band."
    )

    # ── Sprint slippage ───────────────────────────────────────────────────────
    st.divider()
    st.subheader("Sprint Slippage")
    slip = sprint_slippage_summary(df)

    if slip:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Items with sprint data", slip.get("n_items_with_sprint_data", 0))
        c2.metric("No slip",
                  f"{slip.get('n_no_slip', 0)} ({slip.get('pct_no_slip', 0)}%)")
        c3.metric("Slipped 1 sprint",       slip.get("n_slipped_1", 0))
        c4.metric("Slipped 2+ sprints",     slip.get("n_slipped_2plus", 0))
    else:
        st.info("Sprint data not available or insufficient for slippage analysis.")

    # ── Detail table ──────────────────────────────────────────────────────────
    with st.expander("📋 Plan accuracy detail"):
        rows = [{
            "Key": r.key,
            "Title": r.title,
            "Type": r.item_type,
            "Squad": r.squad,
            "Target end": str(r.target_end)[:10] if r.target_end else "",
            "Resolved": str(r.resolved)[:10] if r.resolved else "",
            "Slip (days)": r.slip_days,
            "Sprint planned": r.sprint_planned,
            "Sprint delivered": r.sprint_delivered,
        } for r in sorted(records, key=lambda r: r.slip_days, reverse=True)]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
