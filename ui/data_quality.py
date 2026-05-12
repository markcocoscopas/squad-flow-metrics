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

    if score >= 80:
        colour = "green"
        verdict = "🟢 Excellent — all core metrics are reliable."
        advice  = "Your data is in great shape. Cycle time, throughput, WIP, and forecasts will all be meaningful."
    elif score >= 60:
        colour = "orange"
        verdict = "🟡 Good — most metrics are reliable."
        advice  = "Core flow metrics are solid. Check the breakdown below to see what's missing."
    elif score >= 40:
        colour = "orange"
        verdict = "🟠 Fair — some metrics may be incomplete."
        advice  = "Cycle time and throughput will work but may be based on a limited sample. Review the breakdown below."
    else:
        colour = "red"
        verdict = "🔴 Poor — limited data for meaningful analysis."
        advice  = "Many items are missing dates or being excluded. Check column mapping and filters."

    st.markdown(f"### Data readiness score: :{colour}[{score:.0f} / 100]")
    st.progress(int(score) / 100)
    st.markdown(f"**{verdict}**  \n{advice}")

    # ── Score breakdown ───────────────────────────────────────────────────────
    with st.expander("📋 How the score is calculated", expanded=score < 70):
        ct_pct = report.pct_contributing_cycle_time
        ct_pts = min(60.0, ct_pct * 0.6)
        excl_pct = round(100 * report.rows_excluded / max(report.total_rows_read, 1), 1)
        excl_pts = 20.0 if excl_pct < 5 else (10.0 if excl_pct < 20 else 0.0)
        blocked_pts = 10.0 if report.has_blocked_flag > 0 else 0.0
        plan_pts = 10.0 if report.has_target_end > 0 else 0.0

        def _tick(pts, max_pts):
            return "✅" if pts >= max_pts else ("⚠️" if pts > 0 else "❌")

        st.markdown(
            f"| Component | Score | Max | Status |\n"
            f"|-----------|------:|----:|--------|\n"
            f"| **Cycle-time coverage** — % of items with both Created & Resolved dates | {ct_pts:.0f} | 60 | {_tick(ct_pts, 60)} {ct_pct}% of items eligible |\n"
            f"| **Low exclusion rate** — < 5% of rows excluded | {excl_pts:.0f} | 20 | {_tick(excl_pts, 20)} {excl_pct}% excluded |\n"
            f"| **Blocked flag data** — `Custom field (Blocked)` populated | {blocked_pts:.0f} | 10 | {_tick(blocked_pts, 10)} {'present' if blocked_pts else 'not found — constraints tab limited'} |\n"
            f"| **Plan accuracy data** — Advanced Roadmaps CSV loaded | {plan_pts:.0f} | 10 | {_tick(plan_pts, 10)} {'present' if plan_pts else 'not loaded — plan accuracy tab unavailable'} |\n"
            f"| **Total** | **{score:.0f}** | **100** | |\n"
        )
        st.caption(
            "The score is a data *readiness* indicator, not a quality judgement on your team. "
            "A score below 60 usually means the column mapping needs adjusting, "
            "or the date range filter is too narrow."
        )

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
