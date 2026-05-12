"""
core/plan_accuracy.py
~~~~~~~~~~~~~~~~~~~~~
Bonus v1 features unlocked by joining the Advanced Roadmaps CSV.

Plan accuracy
  How close were the target end dates to actual resolution dates?
  Positive slip = delivered late.  Negative slip = delivered early.

Sprint slippage
  How many items were delivered in a later sprint than planned?
  Requires the compound sprint field to have at least one [COMPLETED] sprint.

Public API
----------
  plan_accuracy_records(df)          → list[PlanAccuracyRecord]
  plan_accuracy_summary(records)     → dict  (summary stats)
  sprint_slippage_summary(df)        → dict  (slippage stats)
"""

from __future__ import annotations

import logging
import re

import numpy as np
import pandas as pd

from core.models import PlanAccuracyRecord

log = logging.getLogger(__name__)

_SECS_PER_DAY = 86_400.0


# ── Plan accuracy ─────────────────────────────────────────────────────────────

def plan_accuracy_records(df: pd.DataFrame) -> list[PlanAccuracyRecord]:
    """
    Build a PlanAccuracyRecord for every resolved item that has a
    rm_target_end date (from the Advanced Roadmaps join).

    Items without both resolved and rm_target_end are skipped.
    """
    required = {"key", "title", "type", "squad", "resolved"}
    if not required.issubset(df.columns) or "rm_target_end" not in df.columns:
        log.info("plan_accuracy_records: required columns not present — returning empty list.")
        return []

    eligible = df[
        df["resolved"].notna() &
        df["rm_target_end"].notna()
    ].copy()

    if eligible.empty:
        return []

    records: list[PlanAccuracyRecord] = []
    for _, row in eligible.iterrows():
        slip = (row["resolved"] - row["rm_target_end"]).total_seconds() / _SECS_PER_DAY

        records.append(PlanAccuracyRecord(
            key=str(row.get("key", "")),
            title=str(row.get("title", ""))[:80],
            item_type=str(row.get("type", "")),
            squad=str(row.get("squad", "")),
            target_end=row["rm_target_end"],
            resolved=row["resolved"],
            slip_days=round(float(slip), 1),
            sprint_planned=str(row.get("sprint_first", "")),
            sprint_delivered=str(row.get("sprint_last_completed", "")),
        ))

    return records


def plan_accuracy_summary(records: list[PlanAccuracyRecord]) -> dict:
    """
    Aggregate plan accuracy statistics.

    Returns a dict with keys:
        n_items, n_on_time, n_late, n_early,
        pct_on_time (delivered within ±3 days of target),
        mean_slip_days, median_slip_days, p85_slip_days
    """
    if not records:
        return {}

    slips = [r.slip_days for r in records]
    arr   = np.array(slips)

    on_time_tolerance = 3.0   # days; items within ±3 days count as "on time"
    n_late    = int((arr > on_time_tolerance).sum())
    n_early   = int((arr < -on_time_tolerance).sum())
    n_on_time = int((np.abs(arr) <= on_time_tolerance).sum())

    return {
        "n_items":          len(records),
        "n_on_time":        n_on_time,
        "n_late":           n_late,
        "n_early":          n_early,
        "pct_on_time":      round(100 * n_on_time / len(records), 1),
        "mean_slip_days":   round(float(arr.mean()), 1),
        "median_slip_days": round(float(np.median(arr)), 1),
        "p85_slip_days":    round(float(np.percentile(arr, 85)), 1),
    }


# ── Sprint slippage ───────────────────────────────────────────────────────────

def _sprint_number(sprint_name: str) -> int | None:
    """
    Extract an integer sprint number from a sprint name.
    Handles common patterns:
      "PMD_26PI1_Sprint3"  → 3
      "Sprint 2"           → 2
      "Sprint2"            → 2
    Returns None if no number found.
    """
    match = re.search(r"sprint\s*(\d+)", sprint_name, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def sprint_slippage_summary(df: pd.DataFrame) -> dict:
    """
    Analyse how many items slipped across one or more sprints.

    Requires:
        sprint_first             — first sprint the item appeared in
        sprint_last_completed    — sprint it was finally resolved in
        resolved                 — non-null means the item is Done

    Returns a dict with keys:
        n_items_with_sprint_data, n_no_slip, n_slipped_1, n_slipped_2plus,
        pct_no_slip, pct_slipped
    """
    required = {"sprint_first", "sprint_last_completed", "resolved"}
    if not required.issubset(df.columns):
        log.info("sprint_slippage_summary: sprint columns not present — returning empty.")
        return {}

    done = df[df["resolved"].notna()].copy()
    done = done[
        done["sprint_first"].notna() &
        (done["sprint_first"] != "") &
        done["sprint_last_completed"].notna() &
        (done["sprint_last_completed"] != "")
    ]

    if done.empty:
        return {}

    done["_n_planned"] = done["sprint_first"].apply(_sprint_number)
    done["_n_delivered"] = done["sprint_last_completed"].apply(_sprint_number)

    # Only count rows where we could extract both numbers
    valid = done[done["_n_planned"].notna() & done["_n_delivered"].notna()].copy()
    if valid.empty:
        return {}

    valid["_slip"] = (valid["_n_delivered"] - valid["_n_planned"]).astype(int)

    n_total     = len(valid)
    n_no_slip   = int((valid["_slip"] == 0).sum())
    n_slip_1    = int((valid["_slip"] == 1).sum())
    n_slip_2p   = int((valid["_slip"] >= 2).sum())
    n_early     = int((valid["_slip"] < 0).sum())  # delivered earlier than planned
    pct_no_slip = round(100 * n_no_slip / max(n_total, 1), 1)
    pct_slipped = round(100 * (n_slip_1 + n_slip_2p) / max(n_total, 1), 1)

    return {
        "n_items_with_sprint_data": n_total,
        "n_no_slip":                n_no_slip,
        "n_slipped_1":              n_slip_1,
        "n_slipped_2plus":          n_slip_2p,
        "n_delivered_early":        n_early,
        "pct_no_slip":              pct_no_slip,
        "pct_slipped":              pct_slipped,
    }
