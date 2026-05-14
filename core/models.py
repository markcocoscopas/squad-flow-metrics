"""
core/models.py
~~~~~~~~~~~~~~
Typed result containers returned by core functions.  Using dataclasses
(not pandas) keeps the interface stable regardless of pandas version.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CycleTimeStats:
    """Descriptive statistics for a cycle-time series."""
    count: int
    p50: float
    p70: float
    p85: float
    p95: float
    mean: float
    min: float
    max: float
    unit: str = "days"


@dataclass(frozen=True)
class ThroughputStats:
    """Weekly throughput summary."""
    mean_per_week: float
    std_per_week: float
    min_per_week: int
    max_per_week: int
    weeks_observed: int


@dataclass(frozen=True)
class McResult:
    """Result of a Monte Carlo simulation run."""
    mode: str                     # "how_many" | "when"
    n_simulations: int
    confidence_levels: List[int]
    # mode="how_many": items completed at each confidence level
    # mode="when":     weeks to completion at each confidence level
    percentile_values: Dict[int, float]
    raw_samples: List[int] = field(default_factory=list, compare=False)


@dataclass
class AgeingItem:
    """A single in-flight item with age and context."""
    key: str
    title: str
    item_type: str
    status: str
    squad: str
    age_days: float
    created: Any          # datetime or date
    p50_reference: float  # 50th-pct historical cycle time for this item type
    p85_reference: float
    p95_reference: float
    is_blocked: bool = False
    is_flagged: bool = False


@dataclass
class ConstraintReport:
    """Summary of constraint/bottleneck indicators."""
    # Blocked-item analysis
    n_blocked: int
    pct_blocked: float
    total_blocked_days: float
    avg_blocked_days: float

    # Age-by-status distribution (state → list of ages in days)
    age_by_status: Dict[str, List[float]] = field(default_factory=dict)

    # WIP breach records: list of dicts {state, wip_limit, current_wip}
    wip_breaches: List[Dict] = field(default_factory=list)

    # Candidate constraint state (highest median age among active states)
    candidate_constraint_state: str = ""
    candidate_constraint_median_days: float = 0.0


@dataclass
class PlanAccuracyRecord:
    """Plan accuracy for a single resolved item."""
    key: str
    title: str
    item_type: str
    squad: str
    target_end: Any        # date or NaT
    resolved: Any          # date or NaT
    slip_days: float       # resolved − target_end (negative = delivered early)
    sprint_planned: str    # first sprint item appeared in
    sprint_delivered: str  # sprint it was marked Done in


@dataclass
class DataQualityReport:
    """Breakdown of rows accepted / excluded and why."""
    total_rows_read: int
    rows_accepted: int
    rows_excluded: int

    # Reason → count
    exclusion_reasons: Dict[str, int] = field(default_factory=dict)

    # Per-metric coverage
    has_resolved: int = 0       # rows with a valid Resolved date
    has_created: int = 0        # rows with a valid Created date
    has_both_dates: int = 0     # rows contributing to cycle-time
    has_blocked_flag: int = 0   # rows with a populated Blocked field
    has_target_end: int = 0     # rows with a Target end date (roadmaps join)

    @property
    def pct_contributing_cycle_time(self) -> float:
        if self.total_rows_read == 0:
            return 0.0
        return round(100 * self.has_both_dates / self.total_rows_read, 1)
