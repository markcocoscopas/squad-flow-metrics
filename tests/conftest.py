"""
tests/conftest.py
~~~~~~~~~~~~~~~~~
Shared pytest fixtures for the Squad Flow Metrics test suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure project root is on the path regardless of how pytest is invoked
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.schema import load_config


# ── Config fixture ────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def default_config():
    return load_config()


# ── Minimal DataFrame factories ───────────────────────────────────────────────

def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Create a minimal DataFrame with all required columns defaulted."""
    defaults = {
        "key": "", "title": "", "type": "Story", "status": "Done",
        "squad": "Alpha Squad", "labels": "", "story_points": None,
        "is_blocked": False, "is_flagged": False, "age_jira": None,
        "sprint_raw": "", "sprint_first": "", "sprint_last_completed": "",
        "epic_link": "", "blocked_raw": "", "flagged_raw": "",
    }
    records = [{**defaults, **r} for r in rows]
    df = pd.DataFrame(records)

    # Ensure datetime columns
    for col in ("created", "resolved"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
        else:
            df[col] = pd.NaT

    return df


@pytest.fixture
def healthy_squad_df():
    """20 resolved items, consistent ~8-day cycle time."""
    import numpy as np
    rng = np.random.default_rng(1)
    rows = []
    for i in range(20):
        created  = pd.Timestamp("2025-11-03") + pd.Timedelta(days=int(rng.integers(0, 80)))
        ct_days  = max(1, int(rng.normal(8, 2)))
        resolved = created + pd.Timedelta(days=ct_days)
        rows.append({
            "key": f"ALPHA-{i+1}",
            "title": f"Story {i+1}",
            "type": rng.choice(["Story", "Bug"]),
            "status": "Done",
            "squad": "Alpha Squad",
            "created": created,
            "resolved": resolved,
        })
    # Add a few in-flight
    for i in range(4):
        created = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i * 3)
        rows.append({
            "key": f"ALPHA-WIP-{i+1}",
            "type": "Story",
            "status": "In Progress",
            "squad": "Alpha Squad",
            "created": created,
            "resolved": None,
        })
    return _make_df(rows)


@pytest.fixture
def bottleneck_squad_df():
    """20 resolved items with long cycle times; several blocked in-flight."""
    import numpy as np
    rng = np.random.default_rng(2)
    rows = []
    for i in range(20):
        created  = pd.Timestamp("2025-11-03") + pd.Timedelta(days=int(rng.integers(0, 80)))
        ct_days  = max(3, int(rng.normal(18, 5)))
        resolved = created + pd.Timedelta(days=ct_days)
        rows.append({
            "key": f"BETA-{i+1}",
            "type": "Story",
            "status": "Done",
            "squad": "Beta Squad",
            "created": created,
            "resolved": resolved,
        })
    # Blocked in-flight
    for i in range(5):
        created = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i * 7)
        rows.append({
            "key": f"BETA-BLK-{i+1}",
            "type": "Story",
            "status": "Blocked",
            "squad": "Beta Squad",
            "created": created,
            "resolved": None,
            "is_blocked": True,
        })
    return _make_df(rows)


@pytest.fixture
def sample_csv_path():
    """Path to the bundled synthetic sample CSV."""
    path = _ROOT / "data" / "sample" / "sample_squads.csv"
    if not path.exists():
        pytest.skip("Sample CSV not found — run generate_sample.py first.")
    return str(path)


@pytest.fixture
def sample_roadmaps_path():
    """Path to the bundled synthetic roadmaps CSV."""
    path = _ROOT / "data" / "sample" / "sample_roadmaps.csv"
    if not path.exists():
        pytest.skip("Sample roadmaps CSV not found.")
    return str(path)
