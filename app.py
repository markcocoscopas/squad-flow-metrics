"""
app.py
~~~~~~
Streamlit entry point for Squad Flow Metrics.

Run with:
    streamlit run app.py

Architecture: this file only wires things together.  All logic lives in
core/ (pure functions) and ui/ (thin Streamlit views).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import streamlit as st

# ── Path setup ────────────────────────────────────────────────────────────────
# Add the project root to sys.path so that `core`, `ui`, `config` are importable
# regardless of the working directory used to launch streamlit.
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_ROOT / "squad_flow.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Imports (after path setup) ────────────────────────────────────────────────
import pandas as pd

from config.schema import load_config
from core.ingest import load_snapshot, load_roadmaps, merge_datasets, apply_filters
from ui.sidebar import render_sidebar

import ui.overview      as tab_overview
import ui.cycle_time    as tab_cycle_time
import ui.throughput    as tab_throughput
import ui.ageing_wip    as tab_ageing
import ui.forecasts     as tab_forecasts
import ui.constraints   as tab_constraints
import ui.plan_accuracy as tab_plan
import ui.compare       as tab_compare
import ui.data_quality  as tab_quality


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Squad Flow Metrics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Session state helpers ─────────────────────────────────────────────────────
def _load_data(
    snapshot_path: str,
    roadmaps_path: str | None,
    config,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Load and merge CSVs, caching by file path."""
    snap_df = load_snapshot(snapshot_path, config)

    rm_df = None
    if roadmaps_path:
        try:
            rm_df = load_roadmaps(roadmaps_path, config)
        except Exception as exc:
            log.warning("Could not load roadmaps CSV: %s", exc)
            st.sidebar.warning(f"Roadmaps CSV skipped: {exc}")

    return snap_df, rm_df


def _get_or_load(state: "SidebarState") -> tuple[pd.DataFrame | None, object | None]:
    """
    Load data if the file paths or config have changed, otherwise reuse cached.
    Returns (merged_df, quality_report).
    """
    cache_key = (state.snapshot_path, state.roadmaps_path)

    if (
        state.refreshed
        or st.session_state.get("_data_cache_key") != cache_key
        or st.session_state.get("_raw_df") is None
    ):
        if not state.snapshot_path:
            return None, None
        try:
            snap_df, rm_df = _load_data(
                state.snapshot_path, state.roadmaps_path, state.config
            )
            merged = merge_datasets(snap_df, rm_df)
            st.session_state["_raw_df"]         = merged
            st.session_state["_data_cache_key"] = cache_key
            log.info("Data loaded and cached. %d rows.", len(merged))
        except Exception as exc:
            log.exception("Failed to load data: %s", exc)
            st.error(f"Failed to load data: {exc}")
            return None, None
    else:
        merged = st.session_state["_raw_df"]

    # Apply filters
    filtered, report = apply_filters(
        merged,
        config=state.config,
        squads=state.selected_squads or None,
        item_types=state.selected_types or None,
        date_from=state.date_from,
        date_to=state.date_to,
    )

    return filtered, report


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    # Render sidebar first (needs raw df for filter options)
    raw_df = st.session_state.get("_raw_df")
    sidebar_state = render_sidebar(df=raw_df)

    # Load / refresh data
    filtered_df, quality_report = _get_or_load(sidebar_state)

    # Persist file paths in session so they survive re-runs
    if sidebar_state.snapshot_path:
        st.session_state["snapshot_path"] = sidebar_state.snapshot_path
    if sidebar_state.roadmaps_path:
        st.session_state["roadmaps_path"] = sidebar_state.roadmaps_path

    config = sidebar_state.config

    # No data yet — show welcome
    if filtered_df is None or filtered_df.empty:
        if sidebar_state.snapshot_path:
            st.warning("No data matches the current filters.")
        else:
            _show_welcome()
        return

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tabs = st.tabs([
        "📊 Overview",
        "⏱ Cycle Time",
        "🚀 Throughput",
        "⏳ Ageing WIP",
        "🔮 Forecasts",
        "🔍 Constraints",
        "🎯 Plan Accuracy",
        "👥 Compare Squads",
        "🔬 Data Quality",
    ])

    with tabs[0]:
        tab_overview.render(filtered_df, config)
    with tabs[1]:
        tab_cycle_time.render(filtered_df, config)
    with tabs[2]:
        tab_throughput.render(filtered_df, config)
    with tabs[3]:
        tab_ageing.render(filtered_df, config)
    with tabs[4]:
        tab_forecasts.render(
            filtered_df, config,
            n_sims=sidebar_state.n_sims,
            mc_window_weeks=sidebar_state.mc_window_weeks,
        )
    with tabs[5]:
        tab_constraints.render(filtered_df, config)
    with tabs[6]:
        tab_plan.render(filtered_df, config)
    with tabs[7]:
        tab_compare.render(filtered_df, config)
    with tabs[8]:
        tab_quality.render(quality_report, config)


def _show_welcome() -> None:
    st.title("📊 Squad Flow Metrics")
    st.markdown(
        """
        Welcome! This tool analyses flow metrics for one or more Agile squads.

        ### Getting started

        1. **Upload your Jira CSV** — use the 'Jira snapshot CSV' uploader in the sidebar.
           This is the standard *Created vs Resolved* export from Jira.

        2. **Optionally upload an Advanced Roadmaps CSV** to unlock plan accuracy
           and sprint slippage metrics.

        3. **Or click 'Load sample data'** in the sidebar to explore with synthetic data.

        ### What you'll get

        | Tab | What it shows |
        |-----|--------------|
        | Overview | Headline KPIs + auto-generated commentary |
        | Cycle Time | Scatterplot with configurable percentile lines |
        | Throughput | Weekly run chart + histogram |
        | Ageing WIP | In-flight items vs historical cycle-time percentiles |
        | Forecasts | Monte Carlo How Many / When |
        | Constraints | Bottleneck signals from age-by-state + blocked items |
        | Plan Accuracy | Target vs actual dates, sprint slippage |
        | Compare Squads | Small-multiples side-by-side view |
        | Data Quality | Exclusion log and data readiness score |

        ---
        *Built on Actionable Agile / Vacanti flow principles.*
        *Forecasts use historical throughput, not story points.*
        """
    )


if __name__ == "__main__":
    main()
