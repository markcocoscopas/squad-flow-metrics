"""
ui/sidebar.py
~~~~~~~~~~~~~
Streamlit sidebar: file upload, squad filter, type filter, date range,
config upload, and refresh.

Returns a SidebarState dataclass consumed by app.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import yaml

from config.schema import AppConfig, load_config, load_config_from_dict


@dataclass
class SidebarState:
    snapshot_path:  str | None       = None
    roadmaps_path:  str | None       = None
    config:         AppConfig | None = None
    selected_squads: list[str]       = field(default_factory=list)
    selected_types:  list[str]       = field(default_factory=list)
    date_from: pd.Timestamp | None   = None
    date_to:   pd.Timestamp | None   = None
    n_sims:    int                   = 10_000
    mc_window_weeks: int             = 12
    refreshed: bool                  = False


def render_sidebar(df: pd.DataFrame | None = None) -> SidebarState:
    """
    Render the sidebar and return the current SidebarState.
    *df* is the currently loaded DataFrame (used to populate squad / type filters).
    """
    state = SidebarState()

    st.sidebar.title("Squad Flow Metrics")
    st.sidebar.markdown("---")

    # ── Data source ───────────────────────────────────────────────────────────
    st.sidebar.subheader("📂 Data Source")

    snap_file = st.sidebar.file_uploader(
        "Jira snapshot CSV",
        type=["csv"],
        key="snapshot_upload",
        help="Upload the 'Created vs Resolved' Jira export.",
    )
    rm_file = st.sidebar.file_uploader(
        "Advanced Roadmaps CSV (optional)",
        type=["csv"],
        key="roadmaps_upload",
        help="Upload the Advanced Roadmaps export to enable plan accuracy metrics.",
    )

    # Save uploaded files to a temp location so core functions can read them
    tmp_dir = Path(st.session_state.get("tmp_dir", "/tmp/squad_flow"))
    tmp_dir.mkdir(parents=True, exist_ok=True)

    if snap_file:
        snap_path = tmp_dir / "snapshot.csv"
        snap_path.write_bytes(snap_file.read())
        state.snapshot_path = str(snap_path)
    elif "snapshot_path" in st.session_state:
        state.snapshot_path = st.session_state["snapshot_path"]

    if rm_file:
        rm_path = tmp_dir / "roadmaps.csv"
        rm_path.write_bytes(rm_file.read())
        state.roadmaps_path = str(rm_path)
    elif "roadmaps_path" in st.session_state:
        state.roadmaps_path = st.session_state["roadmaps_path"]

    # ── Config ────────────────────────────────────────────────────────────────
    st.sidebar.subheader("⚙️ Configuration")
    cfg_file = st.sidebar.file_uploader(
        "Custom config YAML (optional)",
        type=["yaml", "yml"],
        key="config_upload",
        help="Upload a custom column-mapping config. Defaults to built-in Jira mapping.",
    )

    try:
        if cfg_file:
            raw_cfg = yaml.safe_load(cfg_file.read())
            state.config = load_config_from_dict(raw_cfg)
            st.sidebar.success("Custom config loaded.")
        else:
            state.config = load_config()
    except Exception as exc:
        st.sidebar.error(f"Config error: {exc}")
        state.config = load_config()

    # ── Squad filter ──────────────────────────────────────────────────────────
    if df is not None and not df.empty:
        available_squads = sorted(df["squad"].dropna().unique().tolist())
        available_types  = sorted(df["type"].dropna().unique().tolist())

        st.sidebar.subheader("🏃 Filters")
        selected_squads = st.sidebar.multiselect(
            "Squad(s)",
            options=available_squads,
            default=available_squads,
            key="squad_filter",
        )
        selected_types = st.sidebar.multiselect(
            "Work-item type(s)",
            options=available_types,
            default=[
                t for t in available_types
                if t in state.config.work_item_types_include
            ] or available_types,
            key="type_filter",
        )

        min_date = df["created"].min()
        max_date = df["created"].max()
        if pd.notna(min_date) and pd.notna(max_date):
            col1, col2 = st.sidebar.columns(2)
            with col1:
                date_from = st.date_input(
                    "From", value=min_date.date(), min_value=min_date.date(),
                    max_value=max_date.date(), key="date_from"
                )
            with col2:
                date_to = st.date_input(
                    "To", value=max_date.date(), min_value=min_date.date(),
                    max_value=max_date.date(), key="date_to"
                )
            state.date_from = pd.Timestamp(date_from)
            state.date_to   = pd.Timestamp(date_to)

        state.selected_squads = selected_squads
        state.selected_types  = selected_types

    # ── Monte Carlo settings ──────────────────────────────────────────────────
    st.sidebar.subheader("🎲 Forecast Settings")
    state.n_sims = st.sidebar.select_slider(
        "Simulations",
        options=[1_000, 5_000, 10_000, 20_000, 50_000],
        value=10_000,
        key="n_sims",
    )
    state.mc_window_weeks = st.sidebar.number_input(
        "Throughput window (weeks)",
        min_value=4, max_value=52, value=12, step=1,
        key="mc_window",
        help="How many weeks of historical throughput to use for MC sampling.",
    )

    # ── Refresh ───────────────────────────────────────────────────────────────
    st.sidebar.markdown("---")
    state.refreshed = st.sidebar.button("🔄 Refresh", use_container_width=True)

    # ── Sample data shortcut ──────────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.caption("No data yet? Try the bundled sample:")
    if st.sidebar.button("Load sample data", use_container_width=True):
        sample_dir = Path(__file__).parent.parent / "data" / "sample"
        state.snapshot_path = str(sample_dir / "sample_squads.csv")
        state.roadmaps_path = str(sample_dir / "sample_roadmaps.csv")
        st.session_state["snapshot_path"] = state.snapshot_path
        st.session_state["roadmaps_path"]  = state.roadmaps_path
        st.rerun()

    return state
