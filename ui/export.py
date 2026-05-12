"""
ui/export.py — Export tab.

Three export paths:
  1. CSV  — filtered, cleaned work-item data (always available)
  2. HTML — full squad report with charts embedded as interactive Plotly divs
             (no kaleido / WeasyPrint required — works on every platform)
  3. PDF  — same report rendered to PDF via WeasyPrint (optional; not
             available on Windows without extra system libraries)

Individual chart images are also available via the camera icon (📷) that
appears in the top-right corner of every chart when you hover over it.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd
import streamlit as st

from config.schema import AppConfig
from core.models import DataQualityReport

log = logging.getLogger(__name__)


# ── HTML report builder (no kaleido needed) ───────────────────────────────────

def _build_html_report(
    squad_name: str,
    df: pd.DataFrame,
    config: AppConfig,
    quality_report: DataQualityReport | None,
) -> str:
    """
    Build a self-contained HTML report with interactive Plotly charts.
    Uses Plotly's to_html() so no kaleido or WeasyPrint is required.
    Works offline — Plotly JS is embedded inline.
    """
    from core.metrics import (
        cycle_time_stats, cycle_time_by_type,
        throughput_weekly, throughput_stats,
        wip_snapshot, ageing_items,
    )
    from core.constraints import constraint_report
    from core.plan_accuracy import plan_accuracy_records, plan_accuracy_summary, sprint_slippage_summary
    from core.data_quality import format_report, quality_score
    from ui.charts import (
        cycle_time_scatter, throughput_run_chart, throughput_histogram,
        ageing_wip_chart, wip_over_time_chart, age_by_status_box,
    )
    from core.metrics import wip_over_time

    ct      = cycle_time_stats(df)
    ct_by   = cycle_time_by_type(df)
    weekly  = throughput_weekly(df)
    tp      = throughput_stats(weekly)
    wip     = wip_snapshot(df, config)
    ageing  = ageing_items(df, config)
    cr      = constraint_report(df, config)
    pa_recs = plan_accuracy_records(df)
    pa_sum  = plan_accuracy_summary(pa_recs) if pa_recs else {}
    slip    = sprint_slippage_summary(df)

    total_wip    = sum(v for k, v in wip.items() if not k.startswith("["))
    n_over_p85   = sum(1 for i in ageing if i.age_days > i.p85_reference and i.p85_reference > 0)
    dq_bullets   = format_report(quality_report) if quality_report else []
    dq_score_val = quality_score(quality_report) if quality_report else 0

    def _fig_div(fig) -> str:
        """Embed a Plotly figure as a self-contained HTML div (no CDN needed)."""
        return fig.to_html(
            full_html=False,
            include_plotlyjs="inline" if _fig_div._first else False,
            config={"displayModeBar": True, "responsive": True},
        )
    _fig_div._first = True  # only embed plotlyjs once

    def _fig_section(fig) -> str:
        html = _fig_div(fig)
        _fig_div._first = False
        return f'<div class="chart">{html}</div>'

    # ── Charts ────────────────────────────────────────────────────────────────
    ct_chart   = _fig_section(cycle_time_scatter(df))
    tp_chart   = _fig_section(throughput_run_chart(weekly))
    tp_hist    = _fig_section(throughput_histogram(weekly))
    wip_df     = wip_over_time(df, config)
    wip_chart  = _fig_section(wip_over_time_chart(wip_df, config.wip_limits)) if not wip_df.empty else ""
    age_chart  = _fig_section(ageing_wip_chart(ageing))
    constr_chart = _fig_section(age_by_status_box(cr.age_by_status))

    from ui.charts import plan_accuracy_scatter
    pa_chart = _fig_section(plan_accuracy_scatter(pa_recs)) if pa_recs else ""

    # ── CT table rows ─────────────────────────────────────────────────────────
    ct_rows = "".join(
        f"<tr><td>{t}</td><td>{s.count}</td><td>{s.p50:.1f}</td>"
        f"<td>{s.p85:.1f}</td><td>{s.p95:.1f}</td><td>{s.mean:.1f}</td></tr>"
        for t, s in ct_by.items() if s.count > 0
    )

    # ── WIP table rows ────────────────────────────────────────────────────────
    wip_row_parts = []
    for s, v in wip.items():
        if v > 0:
            cls = ' class="breach"' if config.wip_limits.get(s, 9999) < v else ""
            limit = config.wip_limits.get(s, "—")
            wip_row_parts.append(f"<tr{cls}><td>{s}</td><td>{v}</td><td>{limit}</td></tr>")
    wip_rows = "".join(wip_row_parts)

    # ── Ageing table rows ─────────────────────────────────────────────────────
    age_row_parts = []
    for i in ageing[:30]:
        cls = ' class="breach"' if i.age_days > i.p85_reference > 0 else ""
        blocked_icon = "🚫" if i.is_blocked else ""
        age_row_parts.append(
            f"<tr{cls}><td>{i.key}</td><td>{i.title[:50]}</td><td>{i.item_type}</td>"
            f"<td>{i.status}</td><td>{i.age_days:.0f}</td><td>{i.p85_reference:.0f}</td>"
            f"<td>{blocked_icon}</td></tr>"
        )
    age_rows = "".join(age_row_parts)

    # ── Plan accuracy rows ────────────────────────────────────────────────────
    if pa_recs:
        pa_row_parts = []
        for r in sorted(pa_recs, key=lambda x: x.slip_days, reverse=True)[:30]:
            slip_style = ' style="color:#D55E00;font-weight:bold"' if r.slip_days > 3 else ""
            pa_row_parts.append(
                f"<tr><td>{r.key}</td><td>{r.title[:40]}</td>"
                f"<td>{str(r.target_end)[:10]}</td><td>{str(r.resolved)[:10]}</td>"
                f"<td{slip_style}>{r.slip_days:+.0f}d</td>"
                f"<td>{r.sprint_planned}</td><td>{r.sprint_delivered}</td></tr>"
            )
        pa_rows = "".join(pa_row_parts)
    else:
        pa_rows = ""

    # ── DQ bullets ────────────────────────────────────────────────────────────
    dq_items = "".join(
        f"<li>{b.replace('**', '<strong>', 1).replace('**', '</strong>', 1)}</li>"
        for b in dq_bullets
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Squad Flow Report — {squad_name}</title>
<style>
  body {{font-family:"Segoe UI",Arial,sans-serif;font-size:13px;color:#222;
         max-width:1200px;margin:0 auto;padding:24px;background:#fff}}
  h1   {{color:#0072B2;border-bottom:3px solid #0072B2;padding-bottom:8px;margin-top:0}}
  h2   {{color:#0072B2;margin-top:2em;border-bottom:1px solid #cde}}
  h3   {{color:#444;margin-top:1.2em}}
  .kpi-grid {{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0 24px}}
  .kpi {{background:#f0f6ff;border:1px solid #b3d0f7;border-radius:8px;
          padding:12px 20px;min-width:130px;text-align:center}}
  .kpi .val {{font-size:26px;font-weight:700;color:#0072B2}}
  .kpi .lbl {{font-size:11px;color:#666;margin-top:2px}}
  table {{border-collapse:collapse;width:100%;margin:12px 0}}
  th    {{background:#0072B2;color:#fff;padding:7px 10px;text-align:left;font-size:12px}}
  td    {{padding:5px 10px;border-bottom:1px solid #eee;font-size:12px}}
  tr:nth-child(even) td {{background:#f8fbff}}
  .breach td {{background:#fff3cd!important;font-weight:600}}
  .chart {{margin:16px 0;border:1px solid #e0eaf5;border-radius:6px;overflow:hidden}}
  .caveat {{background:#fff8e1;border-left:4px solid #E69F00;padding:10px 14px;
             margin:10px 0;font-size:12px;border-radius:0 4px 4px 0}}
  .ok     {{background:#e8f5e9;border-left:4px solid #009E73;padding:10px 14px;
             margin:10px 0;font-size:12px;border-radius:0 4px 4px 0}}
  .constraint-box {{background:#e3f2fd;border:2px solid #0072B2;border-radius:8px;
                    padding:12px 18px;margin:12px 0}}
  .footer {{margin-top:3em;padding-top:12px;border-top:1px solid #ddd;
             font-size:11px;color:#999;text-align:center}}
  @media print {{.chart {{page-break-inside:avoid}}}}
</style>
</head>
<body>

<h1>Squad Flow Report — {squad_name}</h1>

<div class="caveat">
  <strong>Note:</strong> Cycle times are calculated in calendar days (Resolved − Created),
  which is a lower bound on true elapsed time. Per-state residency analysis is deferred
  to Phase 2 (Jira API integration).
</div>

<!-- ── KPIs ─────────────────────────────────────────────── -->
<div class="kpi-grid">
  <div class="kpi"><div class="val">{ct.p50:.1f}d</div><div class="lbl">Median cycle time</div></div>
  <div class="kpi"><div class="val">{ct.p85:.1f}d</div><div class="lbl">85th-pct cycle time</div></div>
  <div class="kpi"><div class="val">{ct.p95:.1f}d</div><div class="lbl">95th-pct cycle time</div></div>
  <div class="kpi"><div class="val">{tp.mean_per_week:.1f}</div><div class="lbl">Avg items / week</div></div>
  <div class="kpi"><div class="val">{total_wip}</div><div class="lbl">Current WIP</div></div>
  <div class="kpi"><div class="val">{n_over_p85}</div><div class="lbl">Items older than p85</div></div>
</div>

<!-- ── Constraint callout ─────────────────────────────────── -->
{"<div class='constraint-box'>🔍 <strong>Candidate constraint: " + cr.candidate_constraint_state + "</strong> — highest median in-flight age at <strong>" + str(cr.candidate_constraint_median_days) + " days</strong>.</div>" if cr.candidate_constraint_state else ""}

<!-- ── Cycle Time ─────────────────────────────────────────── -->
<h2>Cycle Time</h2>
{ct_chart}
<h3>By work-item type</h3>
<table>
  <tr><th>Type</th><th>Count</th><th>Median (d)</th><th>85th (d)</th><th>95th (d)</th><th>Mean (d)</th></tr>
  {ct_rows}
</table>

<!-- ── Throughput ────────────────────────────────────────── -->
<h2>Throughput</h2>
{tp_chart}
{tp_hist}
<p>Mean: <strong>{tp.mean_per_week:.1f} items/week</strong> &nbsp;|&nbsp;
   Std dev: {tp.std_per_week:.1f} &nbsp;|&nbsp; Range: {tp.min_per_week}–{tp.max_per_week}</p>

<!-- ── WIP ───────────────────────────────────────────────── -->
<h2>WIP Over Time</h2>
{wip_chart}
<h3>Current WIP by state</h3>
<table>
  <tr><th>State</th><th>Current WIP</th><th>WIP Limit</th></tr>
  {wip_rows}
</table>

<!-- ── Ageing WIP ─────────────────────────────────────────── -->
<h2>Ageing WIP</h2>
{age_chart}
<table>
  <tr><th>Key</th><th>Title</th><th>Type</th><th>Status</th>
      <th>Age (d)</th><th>p85 ref (d)</th><th>Blocked</th></tr>
  {age_rows}
</table>

<!-- ── Constraints ────────────────────────────────────────── -->
<h2>Constraints Analysis</h2>
{constr_chart}
<p>Blocked items: <strong>{cr.n_blocked} ({cr.pct_blocked}%)</strong>
   &nbsp;|&nbsp; Total blocked-item age: <strong>{cr.total_blocked_days:.0f}d</strong></p>
{"<div class='caveat'>⚠ WIP limit breaches: " + ", ".join(b["state"] + " (" + str(b["current_wip"]) + "/" + str(b["wip_limit"]) + ")" for b in cr.wip_breaches) + "</div>" if cr.wip_breaches else "<div class='ok'>✓ No WIP limit breaches.</div>"}

<!-- ── Plan Accuracy ──────────────────────────────────────── -->
{"<h2>Plan Accuracy</h2>" + pa_chart + "<table><tr><th>Key</th><th>Title</th><th>Target end</th><th>Resolved</th><th>Slip</th><th>Planned sprint</th><th>Delivered sprint</th></tr>" + pa_rows + "</table>" if pa_recs else "<h2>Plan Accuracy</h2><p><em>No Advanced Roadmaps data loaded.</em></p>"}

<!-- ── Data Quality ───────────────────────────────────────── -->
<h2>Data Quality (score: {dq_score_val:.0f}/100)</h2>
<ul>{dq_items}</ul>

<div class="footer">
  Generated by Squad Flow Metrics &nbsp;·&nbsp;
  Flow-based analysis (Vacanti / Actionable Agile) &nbsp;·&nbsp;
  Forecasts use Monte Carlo sampling from historical throughput — not story points.
</div>
</body>
</html>"""

    return html


# ── Tab renderer ──────────────────────────────────────────────────────────────

def render(
    df: pd.DataFrame,
    config: AppConfig,
    quality_report: DataQualityReport | None = None,
) -> None:
    st.header("Export")

    with st.expander("ℹ️ What you can export", expanded=False):
        st.markdown(
            "**CSV** — the filtered, cleaned work-item data. Use this for further "
            "analysis in Excel or other tools.\n\n"
            "**HTML report** — a full squad report with all charts embedded as "
            "interactive Plotly charts. Opens in any browser. No internet connection "
            "needed. Use your browser's Print → Save as PDF to get a PDF version.\n\n"
            "**Individual charts** — hover over any chart and click the 📷 camera "
            "icon in the top-right toolbar to download it as a PNG."
        )

    if df.empty:
        st.info("No data loaded — nothing to export.")
        return

    squads = sorted(df["squad"].dropna().unique().tolist())

    # ── Section 1: CSV export ─────────────────────────────────────────────────
    st.subheader("📄 Export data as CSV")
    st.caption("The filtered, cleaned work-item data — ready for Excel or further analysis.")

    from core.metrics import cycle_time_series
    export_df = df[["key", "title", "type", "status", "squad", "labels",
                    "created", "resolved", "story_points",
                    "is_blocked", "is_flagged",
                    "sprint_first", "sprint_last_completed"]].copy()
    export_df["cycle_time_days"] = cycle_time_series(df).round(1)

    # Add roadmaps columns if present
    for col in ("rm_target_end", "rm_target_start", "rm_progress_pct", "rm_rag"):
        if col in df.columns:
            export_df[col] = df[col]

    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Download filtered data (.csv)",
        data=csv_bytes,
        file_name="squad_flow_metrics_data.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.divider()

    # ── Section 2: HTML report ────────────────────────────────────────────────
    st.subheader("📊 Export HTML report")
    st.caption(
        "Full report with interactive charts. Opens in any browser. "
        "To get a PDF: open the HTML file in your browser and use "
        "**File → Print → Save as PDF**."
    )

    squad_for_report = st.selectbox(
        "Squad to report on",
        options=["All squads combined"] + squads,
        key="export_squad_select",
    )

    if st.button("⬇️ Generate & download HTML report",
                 use_container_width=True, key="gen_html"):
        with st.spinner("Building report — this takes a few seconds..."):
            try:
                if squad_for_report == "All squads combined":
                    report_df   = df
                    report_name = "All Squads"
                else:
                    report_df   = df[df["squad"] == squad_for_report]
                    report_name = squad_for_report

                html = _build_html_report(
                    squad_name=report_name,
                    df=report_df,
                    config=config,
                    quality_report=quality_report,
                )
                safe_name = report_name.replace(" ", "_").lower()
                st.download_button(
                    label=f"⬇️ Download {report_name} report (.html)",
                    data=html.encode("utf-8"),
                    file_name=f"squad_flow_{safe_name}.html",
                    mime="text/html",
                    use_container_width=True,
                    key="download_html",
                )
                st.success("Report ready — click the button above to download.")
            except Exception as exc:
                st.error(f"Report generation failed: {exc}")
                log.exception("HTML report generation error")

    st.divider()

    # ── Section 3: Individual charts ──────────────────────────────────────────
    st.subheader("🖼️ Download individual charts")
    st.markdown(
        "Every chart in the app has a built-in download toolbar. "
        "**Hover over any chart** and look for the icons that appear in the top-right corner:"
    )
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            "| Icon | Action |\n|---|---|\n"
            "| 📷 Camera | Download chart as PNG |\n"
            "| 🔍 Magnifier | Zoom in |\n"
            "| ↕️ Arrows | Pan / zoom |\n"
            "| 🏠 House | Reset view |"
        )
    with col2:
        st.info(
            "💡 **Tip:** For the best image quality, zoom your browser to 100% "
            "before downloading, and make the chart as large as possible by "
            "expanding your browser window."
        )
