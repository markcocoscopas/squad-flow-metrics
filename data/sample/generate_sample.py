"""
data/sample/generate_sample.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Generate a synthetic dataset of three squads over 26 weeks.

Squad signatures (as per design brief §10):
  Alpha Squad  — healthy flow: moderate WIP, consistent throughput, short cycle times.
  Beta Squad   — Code Review bottleneck: high age in Review state, low throughput.
  Gamma Squad  — High blocker time: many blocked items, erratic throughput.

Run directly to regenerate:
    python data/sample/generate_sample.py

Output: data/sample/sample_squads.csv (Jira snapshot format)
        data/sample/sample_roadmaps.csv (Advanced Roadmaps format)
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SEED = 42
N_WEEKS = 26
START_DATE = datetime(2025, 11, 3)   # Monday

SQUADS = {
    "Alpha Squad": {
        "component": "Alpha Squad",
        "mean_cycle_days": 8,
        "std_cycle_days": 3,
        "weekly_throughput_mean": 5,
        "weekly_throughput_std": 1,
        "blocked_rate": 0.05,
        "wip": 6,
        "review_multiplier": 1.0,    # no bottleneck
        "item_types": {"Story": 0.55, "Bug": 0.25, "Task": 0.15, "Spike": 0.05},
    },
    "Beta Squad": {
        "component": "Beta Squad",
        "mean_cycle_days": 16,
        "std_cycle_days": 6,
        "weekly_throughput_mean": 3,
        "weekly_throughput_std": 1,
        "blocked_rate": 0.08,
        "wip": 10,
        "review_multiplier": 3.5,    # long code review delays
        "item_types": {"Story": 0.60, "Bug": 0.20, "Task": 0.15, "Spike": 0.05},
    },
    "Gamma Squad": {
        "component": "Gamma Squad",
        "mean_cycle_days": 14,
        "std_cycle_days": 8,
        "weekly_throughput_mean": 4,
        "weekly_throughput_std": 2,
        "blocked_rate": 0.30,        # many blocked items
        "wip": 12,
        "review_multiplier": 1.2,
        "item_types": {"Story": 0.50, "Bug": 0.30, "Task": 0.15, "Spike": 0.05},
    },
}

STATUSES_DONE     = ["Done"]
STATUSES_INFLIGHT = ["In Progress", "Implementing", "Review", "Blocked", "To Do", "Funnel"]
PRIORITIES        = ["Must (1)", "Should (2)", "Could (3)", "Won't (4)"]


def weighted_choice(choices: dict[str, float], rng: random.Random) -> str:
    keys   = list(choices.keys())
    weights = list(choices.values())
    return rng.choices(keys, weights=weights, k=1)[0]


def fmt_date(dt: datetime) -> str:
    """
    Format like Jira: '8/May/26 9:21 AM'
    Uses f-strings instead of %-d / %-I to stay portable on Windows.
    """
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.day}/{dt.strftime('%b/%y')} {hour}:{dt.strftime('%M')} {ampm}"


def generate_sprint_field(created: datetime, resolved: datetime | None, squad: str) -> str:
    """
    Generate a realistic compound sprint field string.
    Maps dates to sprint numbers (2-week sprints from START_DATE).
    """
    sprint_duration = 14  # days

    def date_to_sprint(dt: datetime) -> int:
        delta = (dt - START_DATE).days
        return max(1, delta // sprint_duration + 1)

    created_sprint = date_to_sprint(created)

    if resolved is None:
        # Active sprint
        return f"PMD_25PI4_Sprint{created_sprint} [ACTIVE]"

    delivered_sprint = max(created_sprint, date_to_sprint(resolved))

    parts = []
    for sp in range(created_sprint, delivered_sprint):
        parts.append(f"Sprint{sp} [COMPLETED]")
    # Last sprint — completed if resolved, active otherwise
    parts.append(f"Sprint{delivered_sprint} [COMPLETED]" if resolved else f"Sprint{delivered_sprint} [ACTIVE]")

    # Prefix with PI name
    prefix = f"PMD_25PI4_"
    if parts:
        parts[0] = prefix + parts[0]
    return " + ".join(parts)


def main() -> None:
    rng = random.Random(SEED)
    rows = []
    roadmap_rows = []
    item_id = 1000

    for squad_name, cfg in SQUADS.items():
        component = cfg["component"]
        end_date = START_DATE + timedelta(weeks=N_WEEKS)
        current_date = START_DATE

        # Generate items week by week
        for week in range(N_WEEKS):
            week_start = START_DATE + timedelta(weeks=week)
            # How many items completed this week?
            n_done = max(0, int(rng.gauss(
                cfg["weekly_throughput_mean"],
                cfg["weekly_throughput_std"]
            )))

            # How many items created this week (some stay in-flight)?
            n_created = n_done + rng.randint(0, 2)

            for _ in range(n_created):
                item_id += 1
                key = f"AIOP-{item_id}"
                item_type = weighted_choice(cfg["item_types"], rng)

                # Created time: random moment in the week
                created_offset = timedelta(
                    days=rng.randint(0, 4),
                    hours=rng.randint(9, 17),
                    minutes=rng.randint(0, 59),
                )
                created = week_start + created_offset

                # Decide if Done
                is_done = (rng.random() < n_done / max(n_created, 1)) if n_done > 0 else False

                if is_done:
                    cycle = max(1, int(rng.gauss(cfg["mean_cycle_days"], cfg["std_cycle_days"])))
                    resolved = created + timedelta(days=cycle)
                    if resolved > end_date:
                        resolved = None
                        is_done = False
                        status = rng.choice(STATUSES_INFLIGHT)
                    else:
                        status = "Done"
                        n_done -= 1
                else:
                    resolved = None
                    status = rng.choice(STATUSES_INFLIGHT)

                # Blocked flag
                is_blocked = rng.random() < cfg["blocked_rate"]
                if is_blocked and status not in ("Done",):
                    status = "Blocked"

                # Labels
                label_pool = ["backend", "frontend", "infra", "ml", "data-pipeline", "tech-debt", ""]
                label = rng.choice(label_pool)

                # Sprint field
                sprint_str = generate_sprint_field(created, resolved, squad_name)

                # Story points
                sp_choices = [1, 2, 3, 5, 8, 13, ""]
                sp = rng.choices(sp_choices, weights=[5, 10, 15, 20, 15, 5, 10])[0]

                rows.append({
                    "Summary": f"[{squad_name}] Sample work item {item_id}",
                    "Issue key": key,
                    "Issue id": 10_000_000 + item_id,
                    "Issue Type": item_type,
                    "Status": status,
                    "Project key": "AIOP",
                    "Project name": "Perception & Parking SW Group",
                    "Created": fmt_date(created),
                    "Resolved": fmt_date(resolved) if resolved else "",
                    "Component/s": component,
                    "Labels": label,
                    "Custom field (Story Points)": sp,
                    "Custom field (Blocked)": "Impediment" if is_blocked else "",
                    "Custom field (Flagged)": "Impediment" if (is_blocked and rng.random() < 0.5) else "",
                    "Custom field (Age)": (datetime.now() - created).days if resolved is None else "",
                    "Sprint": sprint_str,
                    "Priority": rng.choice(PRIORITIES),
                    "Custom field (Epic Link)": f"AIOP-{rng.randint(100, 200)}",
                    # Dependency links (sparse)
                    "Outward issue link (Dependency)": f"AIOP-{rng.randint(1000, item_id)}" if rng.random() < 0.1 else "",
                    "Inward issue link (Dependency)":  f"AIOP-{rng.randint(1000, item_id)}" if rng.random() < 0.1 else "",
                })

                # Roadmaps row (subset of items have target dates)
                if rng.random() < 0.7:
                    target_start = created - timedelta(days=rng.randint(0, 7))
                    planned_cycle = max(1, int(rng.gauss(cfg["mean_cycle_days"], cfg["std_cycle_days"] * 0.5)))
                    target_end = target_start + timedelta(days=planned_cycle)
                    rag = rng.choices(["", "Green", "Amber", "Red"], weights=[0.5, 0.3, 0.15, 0.05])[0]

                    roadmap_rows.append({
                        "Hierarchy": "Story" if item_type != "Epic" else "Epic",
                        "Title": f"[{squad_name}] Sample work item {item_id}",
                        "Project": "Perception & Parking SW Group",
                        "Releases": "",
                        "Team": squad_name,
                        "Assignee": f"user{rng.randint(1, 8)}",
                        "Sprint": sprint_str,
                        "Target start date": f"{target_start.day}/{target_start.strftime('%b/%y')}",
                        "Target end date":   f"{target_end.day}/{target_end.strftime('%b/%y')}",
                        "Due date": "",
                        "Story points": sp,
                        "Parent": "",
                        "Priority": rng.choice(PRIORITIES),
                        "Labels": label,
                        "Components": component,
                        "Issue key": key,
                        "Issue status": status,
                        "Progress (%)": 100 if status == "Done" else rng.randint(0, 80),
                        "Progress completed (sp)": sp if status == "Done" else "",
                        "Progress remaining (sp)": 0 if status == "Done" else sp,
                        "Progress (%) issue count (IC)": 100 if status == "Done" else rng.randint(0, 80),
                        "To do IC": 0 if status == "Done" else 1,
                        "In progress IC": 0 if status in ("Done", "To Do", "Funnel") else 1,
                        "Done IC": 1 if status == "Done" else 0,
                        "Total IC": 1,
                        "RAG": rag,
                    })

    import csv

    out_dir = Path(__file__).parent

    # Write snapshot CSV
    snapshot_path = out_dir / "sample_squads.csv"
    fieldnames = [
        "Summary", "Issue key", "Issue id", "Issue Type", "Status",
        "Project key", "Project name", "Created", "Resolved",
        "Component/s", "Labels", "Custom field (Story Points)",
        "Custom field (Blocked)", "Custom field (Flagged)",
        "Custom field (Age)", "Sprint", "Priority",
        "Custom field (Epic Link)",
        "Outward issue link (Dependency)", "Inward issue link (Dependency)",
    ]
    with open(snapshot_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Written {len(rows)} rows to {snapshot_path}")

    # Write roadmaps CSV
    roadmaps_path = out_dir / "sample_roadmaps.csv"
    rm_fieldnames = [
        "Hierarchy", "Title", "Project", "Releases", "Team", "Assignee", "Sprint",
        "Target start date", "Target end date", "Due date", "Story points",
        "Parent", "Priority", "Labels", "Components", "Issue key", "Issue status",
        "Progress (%)", "Progress completed (sp)", "Progress remaining (sp)",
        "Progress (%) issue count (IC)", "To do IC", "In progress IC",
        "Done IC", "Total IC", "RAG",
    ]
    with open(roadmaps_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rm_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(roadmap_rows)

    print(f"Written {len(roadmap_rows)} rows to {roadmaps_path}")


if __name__ == "__main__":
    main()
