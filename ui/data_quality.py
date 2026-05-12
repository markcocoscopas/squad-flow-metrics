"""ui/data_quality.py — Data Quality tab."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.data_quality import format_report, quality_score
from core.models import DataQualityReport
from config.schema import AppConfig


def render(report: DataQualityReport | None, config: AppConfig) -> None:
    st.header("Data Quality")

    with st.expander("ℹ️ What this tells you", expanded=False):
        st.markdown(
            "This tab shows what proportion of your data contributed to each metric "
            "and explains what was excluded and why. Nothing is silently dropped — "
            "every exclusion is accounted for here. Use this tab to validate that "
            "the dashboard is using the data you expect."
        )

    if report is None:
        st.info("No data loaded.")
        return

    # ── Score ─────────────────────────────────────────────────────────────────
    score = quality_score(report)
    colour = "green" if score >= 70 else ("orange" if score >= 40 else "red")
    st.markdown(
        f"**Data readiness score: :{colour}[{score:.0f} / 100]**",
        help=(
            "Heuristic score based on cycle-time coverage, exclusion rate, "
            "and availability of optional fields."
        ),
    )

    st.progress(int(score) / 100)

    st.divider()

    # ── Bullets ───────────────────────────────────────────────────────────────
    bullets = format_report(report)
    for b in bullets:
        st.markdown(b)

    st.divider()

    # ── Raw numbers ──────────────────────────────────────────────────────────
    with st.expander("📊 Raw quality numbers"):
        metrics = {
            "Total rows read": report.total_rows_read,
            "Rows accepted": report.rows_accepted,
            "Rows excluded": report.rows_excluded,
            "Has Created date": report.has_created,
            "Has Resolved date": report.has_resolved,
            "Has both dates (cycle-time eligible)": report.has_both_dates,
            "Has Blocked flag": report.has_blocked_flag,
            "Has Roadmaps target end date": report.has_target_end,
            "% contributing to cycle time": f"{report.pct_contributing_cycle_time}%",
        }
        st.table(pd.DataFrame(metrics.items(), columns=["Metric", "Value"]))
