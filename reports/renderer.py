"""
reports/renderer.py
~~~~~~~~~~~~~~~~~~~
Render per-squad HTML and PDF reports using Jinja2 templates.

PDF rendering requires WeasyPrint:
    pip install weasyprint

If WeasyPrint is unavailable (e.g. missing system libs), the tool degrades
gracefully to HTML-only export with a clear warning.

Public API
----------
  render_squad_html(squad_name, df, config, quality_report) → str  (HTML)
  render_squad_pdf(squad_name, df, config, quality_report)  → bytes | None
  render_group_html(dfs, config)                            → str  (HTML)
"""

from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from config.schema import AppConfig
from core.metrics import (
    cycle_time_stats,
    cycle_time_by_type,
    throughput_weekly,
    throughput_stats,
    wip_snapshot,
    ageing_items,
)
from core.constraints import constraint_report
from core.data_quality import format_report, quality_score
from core.models import DataQualityReport

log = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _jinja_env():
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        return Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
        )
    except ImportError:
        raise ImportError("Jinja2 is required for report generation: pip install jinja2")


def _plotly_fig_to_b64(fig) -> str:
    """Convert a Plotly figure to a base64-encoded PNG string."""
    try:
        img_bytes = fig.to_image(format="png", width=900, height=400, scale=1.5)
        return base64.b64encode(img_bytes).decode("utf-8")
    except Exception as exc:
        log.warning("Could not convert chart to image: %s", exc)
        return ""


def _build_squad_context(
    squad_name: str,
    df: pd.DataFrame,
    config: AppConfig,
    quality_report: DataQualityReport | None = None,
) -> dict[str, Any]:
    """Assemble all the template variables for a squad report."""
    from ui.charts import (
        cycle_time_scatter,
        throughput_run_chart,
        ageing_wip_chart,
    )

    ct    = cycle_time_stats(df)
    ct_by = cycle_time_by_type(df)
    weekly = throughput_weekly(df)
    tp    = throughput_stats(weekly)
    wip   = wip_snapshot(df, config)
    ageing = ageing_items(df, config)
    cr    = constraint_report(df, config)

    n_over_p85 = sum(1 for i in ageing if i.age_days > i.p85_reference and i.p85_reference > 0)

    # Charts as base64 PNGs
    ct_img  = _plotly_fig_to_b64(cycle_time_scatter(df))
    tp_img  = _plotly_fig_to_b64(throughput_run_chart(weekly))
    age_img = _plotly_fig_to_b64(ageing_wip_chart(ageing))

    quality_bullets = format_report(quality_report) if quality_report else []
    dq_score = quality_score(quality_report) if quality_report else 0

    return {
        "squad_name":            squad_name,
        "ct":                    ct,
        "ct_by_type":            ct_by,
        "tp":                    tp,
        "wip":                   {k: v for k, v in wip.items() if v > 0},
        "wip_limits":            config.wip_limits,
        "n_over_p85":            n_over_p85,
        "ageing_items":          ageing[:20],   # top 20 oldest
        "constraint_report":     cr,
        "quality_bullets":       quality_bullets,
        "dq_score":              dq_score,
        "ct_chart_b64":          ct_img,
        "tp_chart_b64":          tp_img,
        "age_chart_b64":         age_img,
        "total_resolved":        ct.count,
    }


def render_squad_html(
    squad_name: str,
    df: pd.DataFrame,
    config: AppConfig,
    quality_report: DataQualityReport | None = None,
) -> str:
    """Render the per-squad HTML report. Returns an HTML string."""
    env = _jinja_env()
    template = env.get_template("squad_report.html.j2")
    context = _build_squad_context(squad_name, df, config, quality_report)
    return template.render(**context)


def render_squad_pdf(
    squad_name: str,
    df: pd.DataFrame,
    config: AppConfig,
    quality_report: DataQualityReport | None = None,
) -> bytes | None:
    """
    Render a PDF report for a squad.
    Returns bytes on success, or None if WeasyPrint is unavailable.
    """
    html = render_squad_html(squad_name, df, config, quality_report)
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html, base_url=str(_TEMPLATES_DIR)).write_pdf()
        return pdf_bytes
    except ImportError:
        log.warning("WeasyPrint not installed — PDF export unavailable.")
        return None
    except Exception as exc:
        log.error("PDF render failed: %s", exc)
        return None


def render_group_html(
    dfs: dict[str, pd.DataFrame],
    config: AppConfig,
) -> str:
    """Render a group-level summary HTML report."""
    env = _jinja_env()
    template = env.get_template("group_report.html.j2")

    squad_summaries = []
    for squad_name, df in dfs.items():
        ct = cycle_time_stats(df)
        tp = throughput_stats(throughput_weekly(df))
        cr = constraint_report(df, config)
        squad_summaries.append({
            "name":       squad_name,
            "ct_p50":     round(ct.p50, 1),
            "ct_p85":     round(ct.p85, 1),
            "tp_mean":    round(tp.mean_per_week, 1),
            "constraint": cr.candidate_constraint_state or "—",
        })

    return template.render(squad_summaries=squad_summaries)
