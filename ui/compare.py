"""ui/compare.py — Squad Comparison tab (small multiples)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.metrics import (
    cycle_time_series,
    cycle_time_stats,
    throughput_weekly,
    throughput_stats,
    wip_snapshot,
)
from core.plan_accuracy import plan_accuracy_records, plan_accuracy_summary, sprint_slippage_summary
from config.schema import AppConfig

_PALETTE = ["#E69F00", "#56B4E9", "#009E73", "#F0E442",
            "#0072B2", "#D55E00", "#CC79A7", "#555555"]


def render(df: pd.DataFrame, config: AppConfig) -> None:
    st.header("Compare Squads")

    with st.expander("ℹ️ What this tells you", expanded=False):
        st.markdown(
            "Small-multiples views let you see flow signatures side by side. "
            "**This is a diagnostic view, not a league table.** "
            "A squad with longer cycle times may be tackling harder problems, "
            "have different work composition, or be dealing with more dependencies. "
            "Use this view to ask: *what can we learn from each other?*"
        )

    if df.empty:
        st.info("No data loaded.")
        return

    squads = sorted(df["squad"].dropna().unique().tolist())
    if len(squads) < 2:
        st.info("Load data with at least two squads to use the comparison view.")
        return

    # ── Summary table ─────────────────────────────────────────────────────────
    st.subheader("Summary comparison")
    rows = []
    for squad in squads:
        sdf = df[df["squad"] == squad]
        ct  = cycle_time_stats(sdf)
        tp  = throughput_stats(throughput_weekly(sdf))
        wip = wip_snapshot(sdf, config)
        total_wip = sum(v for k, v in wip.items() if not k.startswith("["))
        rows.append({
            "Squad":          squad,
            "Items resolved": ct.count,
            "Median CT (d)":  round(ct.p50, 1),
            "85th CT (d)":    round(ct.p85, 1),
            "Avg throughput": round(tp.mean_per_week, 1),
            "Current WIP":    total_wip,
        })
    summary_df = pd.DataFrame(rows)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.caption(
        "CT = Cycle time (calendar days). Comparisons are diagnostic — "
        "squad context matters. Do not use this table for performance ranking."
    )

    st.divider()

    # ── Cycle time small multiples ─────────────────────────────────────────────
    st.subheader("Cycle time scatterplots")
    n = len(squads)
    cols = min(n, 3)
    rows_count = (n + cols - 1) // cols

    fig = make_subplots(
        rows=rows_count, cols=cols,
        subplot_titles=squads,
        shared_yaxes=True,
    )

    for idx, squad in enumerate(squads):
        row = idx // cols + 1
        col = idx % cols + 1
        sdf = df[df["squad"] == squad]
        ct  = cycle_time_series(sdf).dropna()

        if ct.empty:
            continue

        resolved_dates = sdf.loc[ct.index, "resolved"]
        colour = _PALETTE[idx % len(_PALETTE)]

        fig.add_trace(
            go.Scatter(
                x=resolved_dates,
                y=ct,
                mode="markers",
                marker=dict(color=colour, size=5, opacity=0.7),
                name=squad,
                showlegend=False,
            ),
            row=row, col=col,
        )

        # p85 line per squad
        p85 = float(np.percentile(ct, 85))
        fig.add_hline(
            y=p85, line_dash="dash", line_color=colour,
            row=row, col=col,
            annotation_text=f"p85: {p85:.0f}d",
            annotation_font=dict(size=9),
        )

    fig.update_layout(
        height=300 * rows_count,
        title_text="Cycle time per squad",
        hovermode="closest",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Throughput small multiples ────────────────────────────────────────────
    st.subheader("Weekly throughput")

    fig2 = make_subplots(
        rows=rows_count, cols=cols,
        subplot_titles=squads,
        shared_yaxes=False,
    )

    for idx, squad in enumerate(squads):
        row = idx // cols + 1
        col = idx % cols + 1
        sdf = df[df["squad"] == squad]
        weekly = throughput_weekly(sdf)

        if weekly.empty:
            continue

        colour = _PALETTE[idx % len(_PALETTE)]
        fig2.add_trace(
            go.Bar(
                x=weekly.index.astype(str),
                y=weekly.values,
                name=squad,
                marker_color=colour,
                opacity=0.8,
                showlegend=False,
            ),
            row=row, col=col,
        )
        # Rolling mean
        rolling = pd.Series(weekly.values).rolling(4, min_periods=1).mean()
        fig2.add_trace(
            go.Scatter(
                x=weekly.index.astype(str),
                y=rolling,
                mode="lines",
                line=dict(color="#000000", width=1.5, dash="dot"),
                showlegend=False,
            ),
            row=row, col=col,
        )

    fig2.update_layout(
        height=280 * rows_count,
        title_text="Weekly throughput per squad",
        barmode="overlay",
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ── Plan accuracy comparison (only if roadmaps data is present) ───────────
    if "rm_target_end" not in df.columns:
        return

    st.divider()
    st.subheader("Plan accuracy comparison")
    st.caption(
        "Requires Advanced Roadmaps CSV. "
        "Shows how closely each squad hit their target end dates."
    )

    # Summary table
    pa_rows = []
    for squad in squads:
        sdf     = df[df["squad"] == squad]
        records = plan_accuracy_records(sdf)
        if not records:
            continue
        s = plan_accuracy_summary(records)
        slip    = sprint_slippage_summary(sdf)
        pa_rows.append({
            "Squad":             squad,
            "Items":             s.get("n_items", 0),
            "On time (±3d)":     f"{s.get('n_on_time', 0)} ({s.get('pct_on_time', 0)}%)",
            "Late":              s.get("n_late", 0),
            "Early":             s.get("n_early", 0),
            "Median slip (d)":   f"{s.get('median_slip_days', 0):+.0f}",
            "Sprint slip %":     f"{slip.get('pct_slipped', '—')}%" if slip else "—",
        })

    if not pa_rows:
        st.info("No items with both a target end date and resolved date in the current filters.")
        return

    st.dataframe(pd.DataFrame(pa_rows), use_container_width=True, hide_index=True)
    st.caption("Median slip: positive = late on average, negative = early on average.")

    st.divider()

    # Small-multiples scatter: slip days vs target date, one panel per squad
    st.subheader("Slip days per squad")
    pa_squads = [r["Squad"] for r in pa_rows]
    n_pa      = len(pa_squads)
    pa_cols   = min(n_pa, 3)
    pa_rows_n = (n_pa + pa_cols - 1) // pa_cols

    fig3 = make_subplots(
        rows=pa_rows_n, cols=pa_cols,
        subplot_titles=pa_squads,
        shared_yaxes=True,
    )

    on_time_colour = "#009E73"   # bluish green
    late_colour    = "#D55E00"   # vermilion
    early_colour   = "#56B4E9"   # sky blue

    for idx, squad in enumerate(pa_squads):
        row = idx // pa_cols + 1
        col = idx % pa_cols + 1
        sdf     = df[df["squad"] == squad]
        records = plan_accuracy_records(sdf)
        if not records:
            continue

        x       = [r.target_end  for r in records]
        y       = [r.slip_days   for r in records]
        keys    = [r.key         for r in records]
        titles_ = [r.title[:35]  for r in records]
        colours = [
            on_time_colour if abs(v) <= 3
            else (late_colour if v > 3 else early_colour)
            for v in y
        ]

        fig3.add_trace(
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
        # Zero line and tolerance band
        fig3.add_hline(y=0,  line_dash="dot",  line_color="#555555", row=row, col=col)
        fig3.add_hline(y=3,  line_dash="dash", line_color="#E69F00", row=row, col=col)
        fig3.add_hline(y=-3, line_dash="dash", line_color="#E69F00", row=row, col=col)

    fig3.update_layout(
        height=320 * pa_rows_n,
        title_text="Slip days vs target end date (🟢 on time  🔴 late  🔵 early)",
        hovermode="closest",
        yaxis_title="Slip (days)",
    )
    st.plotly_chart(fig3, use_container_width=True)
