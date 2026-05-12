# Squad Flow Metrics

A local-web dashboard for flow-based analytics across one or more Agile squads.
Built on [Actionable Agile / Vacanti](https://actionableagile.com/) principles —
throughput and cycle time, not story-point velocity.

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)
![Tests](https://img.shields.io/badge/tests-81%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-87%25-green)

---

## What it does

| Tab | What you get |
|-----|-------------|
| **Overview** | Headline KPIs + auto-generated plain-English commentary |
| **Cycle Time** | Scatterplot with configurable p50/70/85/95 percentile lines |
| **Throughput** | Weekly run chart + histogram of throughput distribution |
| **Ageing WIP** | In-flight items vs historical cycle-time percentile reference lines |
| **Forecasts** | Monte Carlo *How Many?* and *When?* — probabilistic, not velocity-based |
| **Constraints** | Bottleneck signals from age-by-state and blocked-item analysis |
| **Plan Accuracy** | Target end date vs actual, sprint slippage *(requires Roadmaps CSV)* |
| **Compare Squads** | Side-by-side small-multiples — diagnostic, not a league table |
| **Data Quality** | Exclusion log and data readiness score |

> **No story points. No velocity. No estimates.**
> Forecasts sample from your team's actual historical throughput distribution
> using Monte Carlo simulation.

---

## Quick start

### macOS / Linux

```bash
git clone https://github.com/YOUR_ORG/squad-flow-metrics.git
cd squad-flow-metrics
./run.sh
```

### Windows

```
git clone https://github.com/YOUR_ORG/squad-flow-metrics.git
cd squad-flow-metrics
run.bat
```

The launcher creates a virtual environment, installs dependencies, and opens
the app at **http://localhost:8501**.

---

## Manual setup (if you prefer)

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

**Requirements:** Python 3.9 or later. No other system dependencies for core
features. PDF export additionally requires [WeasyPrint system libraries](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html) — HTML
export works without them.

---

## Loading your data

### Option 1 — Sample data (no Jira required)

Click **"Load sample data"** in the sidebar. This loads a synthetic dataset
of three squads over 26 weeks with deliberately different flow signatures
(healthy, Code-Review bottleneck, high-blocker), so every feature can be
explored immediately.

### Option 2 — Your Jira export

1. In Jira, go to **Issues → Search for issues → Export → Export to CSV (all fields)**
   — this is the *Created vs Resolved* snapshot format.
2. *(Optional)* Export the **Advanced Roadmaps** plan view to unlock Plan Accuracy
   and Sprint Slippage tabs.
3. Upload both files via the sidebar uploaders.

> **Data stays local.** The app runs entirely offline. Nothing is sent anywhere.

---

## Column mapping

The default config (`config/default_config.yaml`) is pre-set for the standard
Jira export format used by this project. If your Jira instance uses different
field names, create a custom config YAML and upload it via the sidebar.

Key mappings:

```yaml
columns:
  id:           "Issue key"
  title:        "Summary"
  type:         "Issue Type"
  status:       "Status"
  created:      "Created"
  resolved:     "Resolved"
  squad:        "Component/s"   # ← change this if your squad is in a different field
```

---

## Architecture

```
squad_flow_metrics/
├── app.py                    # Streamlit entry point (wiring only, no logic)
├── config/
│   ├── default_config.yaml   # Column mapping, workflow states, WIP limits
│   └── schema.py             # Config validation
├── core/                     # Pure-function analytics (no UI imports)
│   ├── ingest.py             # CSV loading, deduplication, date parsing, join
│   ├── metrics.py            # Cycle time, throughput, WIP, ageing WIP
│   ├── monte_carlo.py        # Vectorised MC engine (How Many / When)
│   ├── constraints.py        # Bottleneck analysis
│   ├── plan_accuracy.py      # Plan accuracy, sprint slippage
│   ├── data_quality.py       # Exclusion log formatting, quality score
│   └── models.py             # Typed result dataclasses
├── ui/                       # Streamlit tabs (thin — composition only)
│   ├── sidebar.py
│   ├── charts.py             # Shared Plotly chart builders
│   └── ...one file per tab
├── reports/
│   ├── renderer.py           # HTML/PDF report pipeline
│   └── templates/            # Jinja2 templates
├── data/sample/              # Synthetic sample dataset (3 squads, 26 weeks)
└── tests/                    # pytest — 81 tests, 87% coverage on core/
```

The `core/` layer is pure Python with no Streamlit dependency. The same engine
can be wrapped in a CLI or a scheduled job without changing any analytics code.

---

## Running the tests

```bash
source .venv/bin/activate
pytest tests/ -v
pytest tests/ --cov=core --cov-report=term-missing   # with coverage
```

---

## What's not in v1 (Phase 2 roadmap)

| Feature | Why deferred |
|---------|-------------|
| **Cumulative Flow Diagram** | Requires per-item status-change history — not in the Jira CSV export. Available via `GET /rest/api/2/issue/{key}/changelog`. |
| **Flow Efficiency** | Same — needs time-in-active-state per item. |
| **State residency distributions** | Same. |
| **Jira API direct connection** | CSV ingest only in v1. API integration removes the manual export step. |
| **Dependency graph** | Cross-squad link data exists in the CSV; rendering a useful directed graph needs more work. |

---

## Guiding principles

- **Flow over velocity.** Story points are not used anywhere.
- **Probabilistic over deterministic.** Forecasts are distributions with
  percentiles, never single-point estimates.
- **Constraint-aware.** Every view is designed to help identify *where* the
  bottleneck sits, not just *whether* there is one.
- **Lower-bound honesty.** Cycle times are calendar days (Resolved − Created).
  This is a lower bound on true elapsed time, and this is surfaced explicitly
  in every chart that uses it.
- **Squad autonomy preserved.** The Compare Squads tab is diagnostic, not a
  performance ranking.

---

## Licence

MIT — see `LICENCE` file.
