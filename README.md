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

## Download (Windows — no Python required)

> **Just want to run it on Windows?**
> Go to the [**Releases page**](https://github.com/markcocoscopas/squad-flow-metrics/releases/latest),
> download the `.zip` file, extract it anywhere, and double-click
> **"Run Squad Flow Metrics.bat"**. That's it — no Python, no admin rights, no setup.

---

## Quick start (developers)

### macOS / Linux

```bash
git clone https://github.com/markcocoscopas/squad-flow-metrics.git
cd squad-flow-metrics
./run.sh
```

### Windows

> **Before you start:** Make sure Python 3.9+ is installed from
> [python.org](https://www.python.org/downloads/). During installation,
> tick **"Add Python to PATH"** — without this, the launcher cannot find Python.

```
git clone https://github.com/markcocoscopas/squad-flow-metrics.git
cd squad-flow-metrics
run.bat
```

Or double-click `run.bat` in File Explorer.

The launcher creates a virtual environment, installs all dependencies, and
opens the app at **http://localhost:8501**. On first run this takes about
30–60 seconds; subsequent launches are instant.

> **PDF export on Windows:** the HTML report exports fine on all platforms.
> PDF export additionally needs [WeasyPrint system libraries (GTK3)](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html),
> which are complex to install on Windows. HTML is the recommended format
> for sharing with colleagues.

---

## Manual setup (if you prefer)

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

```bat
:: Windows (Command Prompt)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

**Requirements:** Python 3.9 or later. No other system dependencies needed
for all core features and HTML export.

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

## Publishing a new Windows release

When you want to share a new version with colleagues:

```bash
git tag v1.0.1          # bump the number each time
git push origin v1.0.1
```

That's it. GitHub Actions will automatically:
1. Spin up a Windows build server
2. Bundle the app with a self-contained Python (no install needed)
3. Create a zip (~150–250 MB)
4. Attach it to the Releases page with download instructions

The build takes about **5–8 minutes**. You can watch it under the
**Actions** tab on GitHub. When it turns green, the zip is ready to share.

Colleagues just need the link:
`https://github.com/markcocoscopas/squad-flow-metrics/releases/latest`

You can also trigger a test build at any time **without** creating a release
by going to **Actions → Build Windows Package → Run workflow**.

---

## Licence

MIT — see `LICENCE` file.
