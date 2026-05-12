"""ui/constraints.py — Constraints & Bottleneck Analysis tab."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.constraints import constraint_report
from core.metrics import flow_efficiency_note
from config.schema import AppConfig
from ui.charts import age_by_status_box


def render(df: pd.DataFrame, config: AppConfig) -> None:
    st.header("Constraints & Bottlenecks")

    with st.expander("ℹ️ What this tells you", expanded=False):
        st.markdown(
            "The Theory of Constraints tells us that every system has one constraint "
            "(bottleneck) that limits its throughput. This tab helps you identify "
            "where work is piling up.\n\n"
            "Without per-item status-change history (not available in the Jira CSV "
            "export), the analysis uses the *current age* of in-flight items as a "
            "proxy. Items lingering in a particular state are a signal. "
            "Phase 2 will add exact time-in-state data via the Jira API."
        )

    if df.empty:
        st.info("No data loaded.")
        return

    cr = constraint_report(df, config)

    # ── Candidate constraint ──────────────────────────────────────────────────
    if cr.candidate_constraint_state:
        st.success(
            f"🔍 **Candidate constraint: {cr.candidate_constraint_state}** — "
            f"highest median in-flight age at **{cr.candidate_constraint_median_days:.1f} days**."
        )
    else:
        st.info("Not enough in-flight data to identify a candidate constraint.")

    st.divider()

    # ── Blocked items ─────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Blocked items", f"{cr.n_blocked} ({cr.pct_blocked}%)")
    col2.metric("Total blocked-item age (days)",
                f"{cr.total_blocked_days:.0f}",
                help="Sum of ages of all currently blocked items — a lower bound on lost time.")
    col3.metric("Avg blocked-item age (days)", f"{cr.avg_blocked_days:.1f}")

    if cr.n_blocked > 0:
        st.caption(
            "⚠️ Blocked-item ages are a *lower bound* on true blocked duration. "
            "The Jira snapshot CSV does not record when the Blocked flag was set — "
            "only that it is currently set. Phase 2 (Jira API) will add precise blocked durations."
        )

    st.divider()

    # ── Age by status chart ───────────────────────────────────────────────────
    st.subheader("Age distribution by workflow state")
    fig = age_by_status_box(cr.age_by_status)
    st.plotly_chart(fig, use_container_width=True)

    # ── WIP breaches ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader("WIP limit breaches")
    if cr.wip_breaches:
        breach_df = pd.DataFrame(cr.wip_breaches)
        breach_df.columns = ["State", "WIP limit", "Current WIP", "Excess"]
        st.dataframe(breach_df, use_container_width=True, hide_index=True)
    else:
        st.success("No WIP limit breaches detected.")

    # ── Flow efficiency caveat ────────────────────────────────────────────────
    st.divider()
    st.subheader("Flow Efficiency")
    st.info("ℹ️ " + flow_efficiency_note())
