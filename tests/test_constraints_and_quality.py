"""
tests/test_constraints_and_quality.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for core.constraints, core.data_quality, and core.plan_accuracy.
"""

from __future__ import annotations

import pandas as pd
import pytest

from core.constraints import constraint_report
from core.data_quality import format_report, quality_score
from core.models import DataQualityReport
from core.plan_accuracy import (
    plan_accuracy_records,
    plan_accuracy_summary,
    sprint_slippage_summary,
    _sprint_number,
)


# ── Constraints ───────────────────────────────────────────────────────────────

class TestConstraintReport:
    def test_returns_report(self, healthy_squad_df, default_config):
        cr = constraint_report(healthy_squad_df, default_config)
        from core.models import ConstraintReport
        assert isinstance(cr, ConstraintReport)

    def test_blocked_count(self, bottleneck_squad_df, default_config):
        cr = constraint_report(bottleneck_squad_df, default_config)
        # Bottleneck fixture has 5 blocked in-flight items
        assert cr.n_blocked == 5
        assert cr.pct_blocked > 0

    def test_no_blocked_when_none(self, healthy_squad_df, default_config):
        # Healthy squad fixture has no blocked items
        cr = constraint_report(healthy_squad_df, default_config)
        assert cr.n_blocked == 0

    def test_age_by_status_populated(self, bottleneck_squad_df, default_config):
        cr = constraint_report(bottleneck_squad_df, default_config)
        # Should have at least one state with age data
        assert len(cr.age_by_status) > 0
        # All age values should be non-negative
        for ages in cr.age_by_status.values():
            assert all(a >= 0 for a in ages)

    def test_wip_breach_detection(self, default_config):
        """Force a WIP breach on 'In Progress' and confirm it's detected."""
        rows = []
        for i in range(10):  # WIP limit is 6
            created = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
            rows.append({
                "key": f"BREACH-{i}", "title": f"Item {i}", "type": "Story",
                "status": "In Progress", "squad": "Test",
                "created": created, "resolved": None,
                "is_blocked": False, "is_flagged": False,
                "labels": "", "story_points": None, "age_jira": None,
                "sprint_raw": "", "sprint_first": "", "sprint_last_completed": "",
                "epic_link": "", "blocked_raw": "", "flagged_raw": "",
            })
        df = pd.DataFrame(rows)
        df["created"]  = pd.to_datetime(df["created"])
        df["resolved"] = pd.to_datetime(df["resolved"])
        cr = constraint_report(df, default_config)
        breach_states = [b["state"] for b in cr.wip_breaches]
        assert "In Progress" in breach_states

    def test_candidate_constraint_is_highest_median(self, bottleneck_squad_df, default_config):
        cr = constraint_report(bottleneck_squad_df, default_config)
        if cr.candidate_constraint_state:
            # The identified state should have the highest median age
            import numpy as np
            candidate_ages = cr.age_by_status.get(cr.candidate_constraint_state, [])
            if candidate_ages:
                candidate_median = float(np.median(candidate_ages))
                for state, ages in cr.age_by_status.items():
                    if ages and state != cr.candidate_constraint_state:
                        assert candidate_median >= float(np.median(ages)) - 0.1  # float tolerance

    def test_empty_df(self, default_config):
        empty = pd.DataFrame(columns=["key", "status", "created", "resolved",
                                       "is_blocked", "type", "squad"])
        empty["created"]  = pd.Series(dtype="datetime64[ns]")
        empty["resolved"] = pd.Series(dtype="datetime64[ns]")
        empty["is_blocked"] = pd.Series(dtype=bool)
        cr = constraint_report(empty, default_config)
        assert cr.n_blocked == 0
        assert cr.candidate_constraint_state == ""


# ── Data quality ──────────────────────────────────────────────────────────────

class TestDataQuality:
    def _make_report(self, **kwargs) -> DataQualityReport:
        defaults = {
            "total_rows_read": 100,
            "rows_accepted": 80,
            "rows_excluded": 20,
            "exclusion_reasons": {"Cancelled": 20},
            "has_created": 80,
            "has_resolved": 70,
            "has_both_dates": 70,
            "has_blocked_flag": 5,
            "has_target_end": 30,
        }
        defaults.update(kwargs)
        return DataQualityReport(**defaults)

    def test_format_report_returns_list(self):
        report = self._make_report()
        bullets = format_report(report)
        assert isinstance(bullets, list)
        assert len(bullets) > 0

    def test_format_report_contains_key_info(self):
        report = self._make_report()
        text = " ".join(format_report(report))
        assert "100" in text   # total rows
        assert "80" in text    # accepted rows

    def test_quality_score_high_coverage(self):
        report = self._make_report(
            total_rows_read=100, rows_accepted=100, rows_excluded=0,
            has_both_dates=100, has_blocked_flag=1, has_target_end=1,
        )
        score = quality_score(report)
        assert score >= 70

    def test_quality_score_zero_on_empty(self):
        report = DataQualityReport(total_rows_read=0, rows_accepted=0, rows_excluded=0)
        assert quality_score(report) == 0.0

    def test_quality_score_low_coverage(self):
        report = self._make_report(
            total_rows_read=100, rows_accepted=50, rows_excluded=50,
            has_both_dates=10, has_blocked_flag=0, has_target_end=0,
        )
        score = quality_score(report)
        assert score < 50

    def test_pct_contributing_cycle_time(self):
        report = self._make_report(total_rows_read=100, has_both_dates=75)
        assert report.pct_contributing_cycle_time == 75.0

    def test_no_roadmaps_message(self):
        report = self._make_report(has_target_end=0)
        bullets = format_report(report)
        text = " ".join(bullets)
        assert "roadmaps" in text.lower() or "plan accuracy" in text.lower()


# ── Plan accuracy ─────────────────────────────────────────────────────────────

class TestSprintNumber:
    def test_extracts_number(self):
        assert _sprint_number("PMD_26PI1_Sprint3") == 3
        assert _sprint_number("Sprint 12") == 12
        assert _sprint_number("Sprint2") == 2

    def test_returns_none_on_no_match(self):
        assert _sprint_number("No sprint here") is None
        assert _sprint_number("") is None


def _make_plan_df():
    """DataFrame with rm_target_end and resolved, ready for plan accuracy."""
    rows = [
        {
            "key": "PLAN-1", "title": "On time", "type": "Story", "squad": "Alpha",
            "created": pd.Timestamp("2025-12-01"),
            "resolved": pd.Timestamp("2025-12-15"),
            "rm_target_end": pd.Timestamp("2025-12-14"),  # 1 day late
            "sprint_first": "Sprint1",
            "sprint_last_completed": "Sprint1",
            "is_blocked": False, "is_flagged": False,
            "labels": "", "story_points": None, "age_jira": None,
            "sprint_raw": "", "epic_link": "", "blocked_raw": "", "flagged_raw": "",
        },
        {
            "key": "PLAN-2", "title": "Very late", "type": "Bug", "squad": "Alpha",
            "created": pd.Timestamp("2025-12-01"),
            "resolved": pd.Timestamp("2026-01-10"),
            "rm_target_end": pd.Timestamp("2025-12-20"),  # 21 days late
            "sprint_first": "Sprint1",
            "sprint_last_completed": "Sprint3",
            "is_blocked": False, "is_flagged": False,
            "labels": "", "story_points": None, "age_jira": None,
            "sprint_raw": "", "epic_link": "", "blocked_raw": "", "flagged_raw": "",
        },
        {
            "key": "PLAN-3", "title": "Early", "type": "Story", "squad": "Alpha",
            "created": pd.Timestamp("2025-12-01"),
            "resolved": pd.Timestamp("2025-12-10"),
            "rm_target_end": pd.Timestamp("2025-12-20"),  # 10 days early
            "sprint_first": "Sprint1",
            "sprint_last_completed": "Sprint1",
            "is_blocked": False, "is_flagged": False,
            "labels": "", "story_points": None, "age_jira": None,
            "sprint_raw": "", "epic_link": "", "blocked_raw": "", "flagged_raw": "",
        },
        {
            "key": "PLAN-4", "title": "No target", "type": "Story", "squad": "Alpha",
            "created": pd.Timestamp("2025-12-01"),
            "resolved": pd.Timestamp("2025-12-20"),
            "rm_target_end": None,  # excluded from plan accuracy
            "sprint_first": "Sprint2",
            "sprint_last_completed": "Sprint2",
            "is_blocked": False, "is_flagged": False,
            "labels": "", "story_points": None, "age_jira": None,
            "sprint_raw": "", "epic_link": "", "blocked_raw": "", "flagged_raw": "",
        },
    ]
    df = pd.DataFrame(rows)
    df["created"] = pd.to_datetime(df["created"])
    df["resolved"] = pd.to_datetime(df["resolved"])
    df["rm_target_end"] = pd.to_datetime(df["rm_target_end"])
    return df


class TestPlanAccuracy:
    def test_records_excludes_no_target_end(self):
        df = _make_plan_df()
        records = plan_accuracy_records(df)
        keys = {r.key for r in records}
        assert "PLAN-4" not in keys  # no rm_target_end

    def test_records_correct_slip(self):
        df = _make_plan_df()
        records = plan_accuracy_records(df)
        plan1 = next(r for r in records if r.key == "PLAN-1")
        assert plan1.slip_days == 1.0

        plan3 = next(r for r in records if r.key == "PLAN-3")
        assert plan3.slip_days == -10.0  # early

    def test_summary_counts(self):
        df = _make_plan_df()
        records = plan_accuracy_records(df)
        summary = plan_accuracy_summary(records)
        assert summary["n_items"] == 3
        assert summary["n_late"] == 1    # PLAN-2
        assert summary["n_early"] == 1   # PLAN-3

    def test_empty_records(self):
        assert plan_accuracy_summary([]) == {}

    def test_missing_rm_column(self):
        import pandas as pd
        df = pd.DataFrame({"key": ["X"], "title": ["T"], "type": ["Story"],
                           "squad": ["S"], "resolved": [pd.Timestamp("2026-01-01")]})
        df["resolved"] = pd.to_datetime(df["resolved"])
        records = plan_accuracy_records(df)
        assert records == []


class TestSprintSlippage:
    def test_detects_slippage(self):
        df = _make_plan_df()
        result = sprint_slippage_summary(df)
        if result:
            assert "n_slipped_1" in result
            # PLAN-2 slipped from Sprint1 to Sprint3 (2 sprints)
            assert result.get("n_slipped_2plus", 0) >= 1

    def test_no_slip_for_same_sprint(self):
        df = _make_plan_df()
        result = sprint_slippage_summary(df)
        if result:
            # PLAN-1 and PLAN-3 both delivered in Sprint1
            assert result.get("n_no_slip", 0) >= 2

    def test_empty_returns_empty_dict(self):
        import pandas as pd
        df = pd.DataFrame({"resolved": pd.Series(dtype="datetime64[ns]")})
        result = sprint_slippage_summary(df)
        assert result == {}
