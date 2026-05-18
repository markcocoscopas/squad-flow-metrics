"""
core/metrics.py
~~~~~~~~~~~~~~~
Pure functions for flow metrics.  All functions take a filtered DataFrame
(output of core.ingest.apply_filters) and return either a pd.Series, a
pd.DataFrame, or a typed dataclass from core.models.

Functions
---------
  cycle_time_series(df)                  → pd.Series (float, days)
  cycle_time_stats(df, item_types)       → CycleTimeStats
  throughput_daily(df)                   → pd.Series (int, indexed by date)
  throughput_weekly(df, week_anchor)     → pd.Series (int, indexed by period)
  throughput_stats(weekly_series)        → ThroughputStats
  wip_snapshot(df, config)              → dict[str, int]
  wip_over_time(df, freq)               → pd.DataFrame (state → count by period)
  ageing_items(df, config, ref_date)    → list[AgeingItem]
  flow_efficiency_note()                 → str  (caveat message)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Sequence

import numpy as np
import pandas as pd

from config.schema import AppConfig
from core.models import AgeingItem, CycleTimeStats, ThroughputStats

log = logging.getLogger(__name__)

# Days in a work-week when calendar days are used as a proxy.
# NOTE: We use calendar days throughout (not working days) because the
# Jira export does not contain time-in-state data. Calendar-day cycle
# time is a lower bound on working-day cycle time. This is surfaced in
# UI tooltips.
_SECS_PER_DAY = 86_400.0


# ── Cycle time ────────────────────────────────────────────────────────────────

def cycle_time_series(df: pd.DataFrame) -> pd.Series:
    """
    Calculate cycle time (Resolved − Created) in calendar days.

    Returns a float Series indexed the same as *df*, with NaN for rows
    missing either timestamp or with negative cycle time.
    """
    has_both = df["created"].notna() & df["resolved"].notna()
    ct = (df["resolved"] - df["created"]).dt.total_seconds() / _SECS_PER_DAY
    ct = ct.where(has_both)
    ct = ct.where(ct >= 0)     # flag, but don't silently include, negatives
    return ct


def cycle_time_stats(
    df: pd.DataFrame,
    item_types: Sequence[str] | None = None,
) -> CycleTimeStats:
    """
    Descriptive statistics for cycle time, optionally filtered to specific
    work-item types.  Returns a CycleTimeStats dataclass.
    """
    sub = df if not item_types else df[df["type"].isin(item_types)]
    ct = cycle_time_series(sub).dropna()

    if ct.empty:
        return CycleTimeStats(
            count=0, p50=0, p70=0, p85=0, p95=0, mean=0, min=0, max=0,
        )

    return CycleTimeStats(
        count=int(len(ct)),
        p50=float(np.percentile(ct, 50)),
        p70=float(np.percentile(ct, 70)),
        p85=float(np.percentile(ct, 85)),
        p95=float(np.percentile(ct, 95)),
        mean=float(ct.mean()),
        min=float(ct.min()),
        max=float(ct.max()),
    )


def cycle_time_by_type(df: pd.DataFrame) -> dict[str, CycleTimeStats]:
    """Return CycleTimeStats broken down by work-item type."""
    result = {}
    for t in df["type"].dropna().unique():
        result[str(t)] = cycle_time_stats(df, item_types=[t])
    return result


# ── Throughput ────────────────────────────────────────────────────────────────

def throughput_daily(df: pd.DataFrame) -> pd.Series:
    """
    Items completed per calendar day.

    Only counts rows with a valid Resolved date.
    Returns a Series with DatetimeIndex (daily frequency, no gaps filled).
    """
    done = df[df["resolved"].notna()].copy()
    if done.empty:
        return pd.Series(dtype=int, name="throughput_daily")

    daily = (
        done.set_index("resolved")
        .resample("D")["key"]
        .count()
        .rename("throughput_daily")
    )
    return daily


def throughput_weekly(
    df: pd.DataFrame,
    week_anchor: str = "W-MON",
) -> pd.Series:
    """
    Items completed per ISO week (Monday-anchored by default).

    Returns a Series with PeriodIndex (weekly frequency).
    """
    done = df[df["resolved"].notna()].copy()
    if done.empty:
        return pd.Series(dtype=int, name="throughput_weekly")

    weekly = (
        done.set_index("resolved")
        .resample(week_anchor)["key"]
        .count()
        .rename("throughput_weekly")
    )
    return weekly


def throughput_stats(weekly_series: pd.Series) -> ThroughputStats:
    """Descriptive statistics for a weekly throughput Series."""
    s = weekly_series.dropna()
    if s.empty:
        return ThroughputStats(0.0, 0.0, 0, 0, 0)
    return ThroughputStats(
        mean_per_week=float(s.mean()),
        std_per_week=float(s.std(ddof=1)) if len(s) > 1 else 0.0,
        min_per_week=int(s.min()),
        max_per_week=int(s.max()),
        weeks_observed=int(len(s)),
    )


def throughput_samples(
    weekly_series: pd.Series,
    window_weeks: int = 12,
    exclude_dates: "list[tuple[pd.Timestamp, pd.Timestamp]] | None" = None,
) -> list[int]:
    """
    Extract the last *window_weeks* of throughput data as a list of ints,
    suitable for Monte Carlo sampling.

    Parameters
    ----------
    weekly_series   : output of throughput_weekly()
    window_weeks    : how many weeks to look back from the most recent week
    exclude_dates   : list of (start, end) tuples to omit (e.g. holiday shutdowns)

    Returns a list of weekly counts (never empty — returns [0] as fallback).
    """
    s = weekly_series.dropna()
    if s.empty:
        return [0]

    # Take the tail
    s = s.tail(window_weeks)

    # Optionally remove excluded periods
    if exclude_dates:
        for excl_start, excl_end in exclude_dates:
            try:
                s = s[(s.index < excl_start) | (s.index > excl_end)]
            except TypeError:
                pass  # index type mismatch — skip

    samples = s.astype(int).tolist()
    return samples if samples else [0]


# ── WIP ───────────────────────────────────────────────────────────────────────

def wip_snapshot(
    df: pd.DataFrame,
    config: AppConfig,
    ref_date: "pd.Timestamp | None" = None,
) -> dict[str, int]:
    """
    Count of in-flight items per workflow state at *ref_date* (default: now).

    An item is 'in-flight' if it has been created (≤ ref_date) and not yet
    resolved (resolved > ref_date, or no resolved date).
    """
    if ref_date is None:
        ref_date = pd.Timestamp.now(tz=None)

    in_flight = df[
        (df["created"].notna()) &
        (df["created"] <= ref_date) &
        (df["resolved"].isna() | (df["resolved"] > ref_date))
    ]

    counts: dict[str, int] = {}
    for state in config.state_order:
        n = int((in_flight["status"] == state).sum())
        counts[state] = n

    # Also capture any statuses not in the workflow definition (so we don't hide them)
    untracked = in_flight[~in_flight["status"].isin(config.state_order)]["status"].value_counts()
    for status, n in untracked.items():
        counts[f"[{status}]"] = int(n)

    return counts


def wip_over_time(
    df: pd.DataFrame,
    config: AppConfig,
    freq: str = "W-MON",
) -> pd.DataFrame:
    """
    Weekly WIP count per workflow state.

    Uses a date range from earliest creation to latest resolution (or today),
    re-sampling at *freq*.

    Returns a DataFrame with columns = state names, index = period end dates.
    """
    if df.empty or df["created"].isna().all():
        return pd.DataFrame()

    start = df["created"].min()
    end   = df["resolved"].max() if df["resolved"].notna().any() else pd.Timestamp.now()

    periods = pd.date_range(start=start, end=end, freq=freq)
    states  = config.state_order

    rows = []
    for period_end in periods:
        wip = wip_snapshot(df, config, ref_date=period_end)
        row = {s: wip.get(s, 0) for s in states}
        row["_date"] = period_end
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows).set_index("_date")
    return result


# ── Ageing WIP ───────────────────────────────────────────────────────────────

def ageing_items(
    df: pd.DataFrame,
    config: AppConfig,
    ref_date: "pd.Timestamp | None" = None,
) -> list[AgeingItem]:
    """
    All currently in-flight items (no resolved date), annotated with:
      - age in calendar days since creation
      - 50th / 85th / 95th percentile reference lines from historical
        cycle-time distribution (filtered to same item type)
      - blocked / flagged flags

    Items are sorted by age descending (oldest first).
    """
    if ref_date is None:
        ref_date = pd.Timestamp.now(tz=None)

    in_flight = df[df["resolved"].isna() & df["created"].notna()].copy()
    if in_flight.empty:
        return []

    # Historical cycle times per type for reference lines
    ct_by_type: dict[str, tuple[float, float, float]] = {}
    done = df[df["resolved"].notna() & df["created"].notna()].copy()
    ct_series = cycle_time_series(done).dropna()

    for itype in df["type"].dropna().unique():
        type_ct = ct_series[done["type"] == itype].dropna()
        if not type_ct.empty:
            ct_by_type[str(itype)] = (
                float(np.percentile(type_ct, 50)),
                float(np.percentile(type_ct, 85)),
                float(np.percentile(type_ct, 95)),
            )
        else:
            all_ct = ct_series.dropna()
            if not all_ct.empty:
                ct_by_type[str(itype)] = (
                    float(np.percentile(all_ct, 50)),
                    float(np.percentile(all_ct, 85)),
                    float(np.percentile(all_ct, 95)),
                )
            else:
                ct_by_type[str(itype)] = (0.0, 0.0, 0.0)

    items = []
    for _, row in in_flight.iterrows():
        age = (ref_date - row["created"]).total_seconds() / _SECS_PER_DAY
        itype = str(row.get("type", ""))
        p50, p85, p95 = ct_by_type.get(itype, (0.0, 0.0, 0.0))
        items.append(AgeingItem(
            key=str(row.get("key", "")),
            title=str(row.get("title", ""))[:80],
            item_type=itype,
            status=str(row.get("status", "")),
            squad=str(row.get("squad", "")),
            age_days=round(age, 1),
            created=row["created"],
            p50_reference=p50,
            p85_reference=p85,
            p95_reference=p95,
            is_blocked=bool(row.get("is_blocked", False)) or str(row.get("status", "")).lower() == "blocked",
            is_flagged=bool(row.get("is_flagged", False)),
        ))

    items.sort(key=lambda x: x.age_days, reverse=True)
    return items


# ── Flow efficiency (degraded gracefully) ─────────────────────────────────────

def flow_efficiency_note() -> str:
    """
    Return the standard caveat string for flow efficiency.

    Flow efficiency requires time-in-active-states ÷ total-cycle-time.
    Without per-item status change history (not present in the Jira snapshot
    CSV export), this metric cannot be calculated.  Return a caveat string
    for display in the UI rather than silently omitting the section.
    """
    return (
        "Flow efficiency requires per-item status-change history, which is not "
        "available in the standard Jira CSV export. This metric will become "
        "available in Phase 2 when the Jira REST API changelog endpoint "
        "(/rest/api/2/issue/{key}/changelog) is integrated."
    )
