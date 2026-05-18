"""ui/constraints.py — Constraints & Bottleneck Analysis tab."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.constraints import constraint_report
from core.metrics import flow_efficiency_note
from config.schema import AppConfig
from ui.charts import age_by_status_box


def render(df: pd.DataFrame, config: AppConfig) -> None:
    st.header("Constraints & Bottlenecks")

    with st.expander("ℹ️ What this tells you", expanded=False):
        st.markdown(
            """
**The core idea — every system has one bottleneck**

The Theory of Constraints (Goldratt) says that in any flow of work, there is
always *one* step that limits how fast everything else can move. It doesn't
matter how fast the other steps are — the constraint sets the pace for the
whole system. Improving anything that isn't the constraint produces no
meaningful benefit.

**How to find it**

If work is piling up in front of a particular state, that state is likely
your constraint. Items spend longer there than anywhere else — they queue,
age, and wait. The **Age distribution chart** below shows this directly:
the state with the highest median age (the line in the middle of the box)
is the candidate constraint.

**How to read the box plot**

Each box represents one workflow state. Reading from bottom to top:
- The **bottom whisker** is the youngest item in that state
- The **bottom of the box** is the 25th percentile (25% of items are younger than this)
- The **line in the middle** is the median — half the items are older, half are younger
- The **top of the box** is the 75th percentile
- The **top whisker** is the oldest item (excluding outliers)
- **Dots** above the whisker are outliers — unusually old items that deserve attention

A **tall box** means ages vary widely (unpredictable). A **high box** means
items are generally old in that state. The state with the highest median is
your candidate constraint.

**What to do with this**

Once you've identified the constraint state, ask:
- *Why do items get stuck here?* (skill bottleneck, unclear criteria, too much WIP?)
- *Is there a WIP limit breach in this state?* (shown below the chart)
- *Are the blocked items concentrated here?*

Fixing the constraint — not the fastest step — is what increases throughput.

> **Limitation:** Without per-item status-change history (not in the Jira CSV
> export), this analysis uses the *current age since creation* as a proxy for
> time spent in each state. It is directionally correct but not exact.
> Precise time-in-state data requires the Jira API (Phase 2).
            """
        )

    if df.empty:
        st.info("No data loaded.")
        return

    cr = constraint_report(df, config)

    # ── Candidate constraint ──────────────────────────────────────────────────
    if cr.candidate_constraint_state:
        state      = cr.candidate_constraint_state
        median_age = cr.candidate_constraint_median_days
        n_items    = len(cr.age_by_status.get(state, []))

        if n_items < 3:
            # Too few items to be statistically meaningful — flag as anecdotal
            st.info(
                f"🔍 **Candidate constraint: {state}** — "
                f"median age **{median_age:.1f} days** "
                f"(but only **n={n_items}** item{'s' if n_items != 1 else ''} in this state). "
                f"With so few items this is anecdotal, not a systemic signal. "
                f"Monitor over time before acting."
            )
        else:
            st.warning(
                f"🔍 **Candidate constraint: {state}** — "
                f"this state has the highest median in-flight item age at "
                f"**{median_age:.1f} days** (n={n_items} items). "
                f"Work is accumulating here more than anywhere else. "
                f"This is where to focus improvement effort first."
            )
    else:
        st.info("Not enough in-flight data to identify a candidate constraint.")

    st.divider()

    # ── Blocked items ─────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Blocked items",
        f"{cr.n_blocked} ({cr.pct_blocked}%)",
        help="Items currently in the 'Blocked' workflow state OR with the Blocked custom field set.",
    )
    col2.metric(
        "Total blocked-item age (days)",
        f"{cr.total_blocked_days:.0f}",
        help="Sum of ages of all currently blocked items — a lower bound on lost time.",
    )
    col3.metric("Avg blocked-item age (days)", f"{cr.avg_blocked_days:.1f}")

    if cr.n_blocked > 0:
        st.caption(
            "⚠️ An item counts as blocked if it is in the **'Blocked' workflow state** "
            "or has the **Blocked custom field** set. "
            "Ages shown are time since the item was *created* — a lower bound on true blocked duration "
            "since the exact date blocking started is not in the Jira CSV export."
        )

    st.divider()

    # ── Age by status chart ───────────────────────────────────────────────────
    st.subheader("Age distribution by workflow state")
    st.caption(
        "Each box shows the spread of item ages currently sitting in that workflow state. "
        "The **middle line** is the median age. The **state with the highest median** "
        "is your candidate constraint — work is accumulating there. "
        "Hover over any box for exact values."
    )
    fig = age_by_status_box(cr.age_by_status)
    st.plotly_chart(fig, use_container_width=True)

    # ── WIP breaches ──────────────────────────────────────────────────────────
    st.divider()
    st.subheader("WIP limit breaches")
    st.caption(
        "WIP (Work In Progress) limits cap how many items can be in a given state at once. "
        "Exceeding a limit is a signal that work is piling up faster than it is leaving. "
        "High WIP increases average cycle time for *everyone* — it doesn't speed things up, "
        "it slows everything down. Reducing WIP at the constraint is usually the highest-leverage action."
    )
    if cr.wip_breaches:
        breach_df = pd.DataFrame(cr.wip_breaches)
        breach_df.columns = ["State", "WIP limit", "Current WIP", "Excess"]
        st.dataframe(breach_df, use_container_width=True, hide_index=True)
    else:
        st.success("✅ No WIP limit breaches detected.")

    # ── Flow efficiency caveat ────────────────────────────────────────────────
    st.divider()
    st.subheader("Flow Efficiency")
    st.info("ℹ️ " + flow_efficiency_note())
