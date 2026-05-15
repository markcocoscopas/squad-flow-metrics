"""ui/plan_accuracy.py — Plan Accuracy & Sprint Slippage tab."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.plan_accuracy import (
    plan_accuracy_records,
    plan_accuracy_summary,
    sprint_slippage_summary,
)
from config.schema import AppConfig
from ui.charts import plan_accuracy_scatter

_ON_TIME_COLOUR = "#009E73"   # bluish green
_LATE_COLOUR    = "#D55E00"   # vermilion
_EARLY_COLOUR   = "#56B4E9"   # sky blue


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

    squads = sorted(df["squad"].dropna().unique().tolist())

    # ── Sub-tabs: Overall vs By Squad ─────────────────────────────────────────
    if len(squads) > 1:
        overall_tab, by_squad_tab = st.tabs(["📊 Overall", "👥 By Squad"])
    else:
        overall_tab = st.container()
        by_squad_tab = None

    # ── Overall ───────────────────────────────────────────────────────────────
    with overall_tab:
        records = plan_accuracy_records(df)

        if not records:
            st.info(
                "No items have both a target end date and a resolved date in the "
                "selected filters."
            )
        else:
            summary = plan_accuracy_summary(records)

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Items analysed", summary.get("n_items", 0))
            c2.metric("On time (±3d)",
                      f"{summary.get('pct_on_time', 0)}%",
                      help=f"{summary.get('n_on_time', 0)} items delivered within ±3 days of target")
            c3.metric("Late",
                      summary.get("n_late", 0),
                      help="Delivered more than 3 days after target end date")
            c4.metric("Early",
                      summary.get("n_early", 0),
                      help="Delivered more than 3 days before target end date")
            c5.metric("Median slip",
                      f"{summary.get('median_slip_days', 0):+.0f} d",
                      help="Positive = late on average, negative = early on average")

            st.divider()

            fig = plan_accuracy_scatter(records)
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "Colours: 🟢 on time (within ±3 days), 🔴 late, 🔵 early. "
                "Dashed lines show the ±3-day tolerance band."
            )

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

            with st.expander("📋 Plan accuracy detail"):
                rows = [{
                    "Key":               r.key,
                    "Title":             r.title,
                    "Type":              r.item_type,
                    "Squad":             r.squad,
                    "Target end":        str(r.target_end)[:10] if r.target_end else "",
                    "Resolved":          str(r.resolved)[:10]   if r.resolved   else "",
                    "Slip (days)":       r.slip_days,
                    "Sprint planned":    r.sprint_planned,
                    "Sprint delivered":  r.sprint_delivered,
                } for r in sorted(records, key=lambda r: r.slip_days, reverse=True)]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── By Squad ──────────────────────────────────────────────────────────────
    if by_squad_tab is None:
        return

    with by_squad_tab:
        # Summary table
        pa_rows = []
        for squad in squads:
            sdf     = df[df["squad"] == squad]
            records = plan_accuracy_records(sdf)
            if not records:
                continue
            s    = plan_accuracy_summary(records)
            slip = sprint_slippage_summary(sdf)
            pa_rows.append({
                "Squad":           squad,
                "Items":           s.get("n_items", 0),
                "On time %":       f"{s.get('pct_on_time', 0)}%",
                "On time (n)":     s.get("n_on_time", 0),
                "Late":            s.get("n_late", 0),
                "Early":           s.get("n_early", 0),
                "Median slip (d)": f"{s.get('median_slip_days', 0):+.0f}",
                "Sprint slip %":   f"{slip.get('pct_slipped', '—')}%" if slip else "—",
            })

        if not pa_rows:
            st.info("No items with both a target end date and resolved date in the current filters.")
            return

        st.dataframe(pd.DataFrame(pa_rows), use_container_width=True, hide_index=True)
        st.caption("Median slip: positive = late on average, negative = early on average.")

        st.divider()

        # Small-multiples scatter: one panel per squad
        n      = len(pa_rows)
        n_cols = min(n, 3)
        n_rows = (n + n_cols - 1) // n_cols
        pa_squads = [r["Squad"] for r in pa_rows]

        fig = make_subplots(
            rows=n_rows, cols=n_cols,
            subplot_titles=pa_squads,
            shared_yaxes=True,
        )

        for idx, squad in enumerate(pa_squads):
            row = idx // n_cols + 1
            col = idx % n_cols + 1
            sdf     = df[df["squad"] == squad]
            records = plan_accuracy_records(sdf)
            if not records:
                continue

            x       = [r.target_end  for r in records]
            y       = [r.slip_days   for r in records]
            keys    = [r.key         for r in records]
            titles_ = [r.title[:35]  for r in records]
            colours = [
                _ON_TIME_COLOUR if abs(v) <= 3
                else (_LATE_COLOUR if v > 3 else _EARLY_COLOUR)
                for v in y
            ]

            fig.add_trace(
                go.Scatter(
                    x=x, y=y,
                    mode="markers",
                    marker=dict(color=colours, size=7, opacity=0.8),
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "%{customdata[1]}<br>"
                        "Slip: %{y:+.0f}d<extra></extra>"
                    ),
                    customdata=list(zip(keys, titles_)),
                    showlegend=False,
                ),
                row=row, col=col,
            )
            fig.add_hline(y=0,  line_dash="dot",  line_color="#555555", row=row, col=col)
            fig.add_hline(y=3,  line_dash="dash", line_color="#E69F00", row=row, col=col)
            fig.add_hline(y=-3, line_dash="dash", line_color="#E69F00", row=row, col=col)

        fig.update_layout(
            height=340 * n_rows,
            title_text="Slip days vs target end date  (🟢 on time  🔴 late  🔵 early)",
            hovermode="closest",
            yaxis_title="Slip (days)",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Sprint slippage per squad
        st.divider()
        st.subheader("Sprint Slippage by Squad")
        slip_rows = []
        for squad in squads:
            sdf  = df[df["squad"] == squad]
            slip = sprint_slippage_summary(sdf)
            if not slip:
                continue
            slip_rows.append({
                "Squad":              squad,
                "Items w/ sprint":    slip.get("n_items_with_sprint_data", 0),
                "No slip":            f"{slip.get('n_no_slip', 0)} ({slip.get('pct_no_slip', 0)}%)",
                "Slipped 1 sprint":   slip.get("n_slipped_1", 0),
                "Slipped 2+ sprints": slip.get("n_slipped_2plus", 0),
                "Slip %":             f"{slip.get('pct_slipped', 0)}%",
            })
        if slip_rows:
            st.dataframe(pd.DataFrame(slip_rows), use_container_width=True, hide_index=True)
        else:
            st.info("Sprint data not available for any squad.")
