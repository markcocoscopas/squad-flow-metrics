"""
core/monte_carlo.py
~~~~~~~~~~~~~~~~~~~
Vectorised Monte Carlo engine for flow-based forecasting.

Two modes
---------
  how_many(samples, n_days, n_sims)
      Given N working days, what is the distribution of items we will complete?
      Returns McResult with mode="how_many".

  when(samples, backlog, n_sims)
      Given a backlog of N items, what is the distribution of weeks to Done?
      Returns McResult with mode="when".

Design notes
------------
- Sampling is from the empirical weekly throughput distribution — the same
  approach as the v2.7 Monte Carlo tool, so results are consistent
  (acceptance criterion 3 in the design brief).
- Vectorised with numpy: draw (n_sims × max_periods) at once, then use
  cumsum + argmax to find the crossing point.  ~100× faster than a
  Python while-loop.
- Parallelised with multiprocessing.Pool for n_sims > 5 000.
- The RNG seed is not fixed by default (reproducible forecasts can be
  requested by passing seed= to each function).
"""

from __future__ import annotations

import logging
import multiprocessing
from typing import Sequence

import numpy as np

from core.models import McResult

log = logging.getLogger(__name__)

# Upper bound on simulation periods to avoid infinite loops with zero-throughput data
_MAX_PERIODS = 2_000

# Parallelism threshold: above this n_sims, use multiprocessing
_PARALLEL_THRESHOLD = 5_000

# Number of worker processes (None → cpu_count)
_N_WORKERS: int | None = None


# ── Internal vectorised kernels ───────────────────────────────────────────────

def _vectorised_when(
    samples: list[int],
    backlog: int,
    n_sims: int,
    seed: int | None,
) -> np.ndarray:
    """
    Vectorised 'when' kernel.
    Returns 1-D array of week counts (length n_sims).
    """
    rng = np.random.default_rng(seed)
    draws = rng.choice(samples, size=(n_sims, _MAX_PERIODS), replace=True)
    cumsum = np.cumsum(draws, axis=1)
    crossed = cumsum >= backlog
    # argmax returns index of first True; if never True, returns 0 (handle below)
    idx = np.argmax(crossed, axis=1)
    never_crossed = ~crossed.any(axis=1)
    idx[never_crossed] = _MAX_PERIODS - 1
    return idx + 1   # 1-indexed weeks


def _vectorised_how_many(
    samples: list[int],
    n_days: int,
    n_sims: int,
    seed: int | None,
) -> np.ndarray:
    """
    Vectorised 'how many' kernel.
    Converts n_days to weeks (ceiling), then samples that many weekly values.
    Returns 1-D array of item counts (length n_sims).
    """
    import math
    n_weeks = math.ceil(n_days / 7)
    rng = np.random.default_rng(seed)
    # Draw n_weeks throughput values per simulation
    draws = rng.choice(samples, size=(n_sims, n_weeks), replace=True)
    totals = draws.sum(axis=1)
    return totals


# ── Chunked worker (for multiprocessing) ─────────────────────────────────────

def _when_chunk(args: tuple) -> list[int]:
    samples, backlog, chunk_size, seed = args
    return _vectorised_when(samples, backlog, chunk_size, seed).tolist()


def _how_many_chunk(args: tuple) -> list[int]:
    samples, n_days, chunk_size, seed = args
    return _vectorised_how_many(samples, n_days, chunk_size, seed).tolist()


# ── Public API ────────────────────────────────────────────────────────────────

def how_many(
    samples: list[int],
    n_days: int,
    n_sims: int = 10_000,
    confidence_levels: Sequence[int] = (50, 70, 85, 95),
    seed: int | None = None,
) -> McResult:
    """
    Monte Carlo "How Many": given *n_days* working days, how many items
    will we complete?

    Parameters
    ----------
    samples           : list of weekly throughput values (empirical history)
    n_days            : forecast horizon in calendar days
    n_sims            : number of simulations to run
    confidence_levels : percentiles to report (e.g. [50, 70, 85, 95])
    seed              : optional RNG seed for reproducibility

    Returns
    -------
    McResult with mode="how_many" and percentile_values dict.
    At the 85th percentile we are 85% confident we will complete *at least*
    that many items.
    """
    if not samples or all(s == 0 for s in samples):
        log.warning("MC how_many: all samples are zero — returning zero forecast.")
        return McResult(
            mode="how_many",
            n_simulations=n_sims,
            confidence_levels=list(confidence_levels),
            percentile_values={c: 0 for c in confidence_levels},
            raw_samples=[],
        )

    raw = _run_sims(_how_many_chunk, (samples, n_days), n_sims, seed)

    # "How many": higher percentile = more conservative (fewer items)
    # Convention: p85 means "85% chance of completing AT LEAST this many"
    # → use lower percentile of the distribution (100 - conf)
    pv = {
        int(c): int(np.percentile(raw, 100 - c))
        for c in confidence_levels
    }

    return McResult(
        mode="how_many",
        n_simulations=n_sims,
        confidence_levels=list(confidence_levels),
        percentile_values=pv,
        raw_samples=raw,
    )


def when(
    samples: list[int],
    backlog: int,
    n_sims: int = 10_000,
    confidence_levels: Sequence[int] = (50, 70, 85, 95),
    seed: int | None = None,
) -> McResult:
    """
    Monte Carlo "When": given a backlog of *backlog* items, how many weeks
    until they are all Done?

    Parameters
    ----------
    samples           : list of weekly throughput values
    backlog           : number of items remaining
    n_sims            : number of simulations
    confidence_levels : percentiles to report
    seed              : optional RNG seed

    Returns
    -------
    McResult with mode="when".
    At the 85th percentile we are 85% confident we will finish WITHIN that
    many weeks.
    """
    if backlog <= 0:
        return McResult(
            mode="when",
            n_simulations=n_sims,
            confidence_levels=list(confidence_levels),
            percentile_values={c: 0 for c in confidence_levels},
            raw_samples=[],
        )

    if not samples or all(s == 0 for s in samples):
        log.warning("MC when: all samples are zero — returning max-periods forecast.")
        return McResult(
            mode="when",
            n_simulations=n_sims,
            confidence_levels=list(confidence_levels),
            percentile_values={c: _MAX_PERIODS for c in confidence_levels},
            raw_samples=[_MAX_PERIODS] * n_sims,
        )

    raw = _run_sims(_when_chunk, (samples, backlog), n_sims, seed)

    # "When": higher percentile = more conservative (more weeks)
    pv = {
        int(c): int(np.percentile(raw, c))
        for c in confidence_levels
    }

    return McResult(
        mode="when",
        n_simulations=n_sims,
        confidence_levels=list(confidence_levels),
        percentile_values=pv,
        raw_samples=raw,
    )


# ── Shared dispatcher ─────────────────────────────────────────────────────────

def _run_sims(
    worker_fn,
    extra_args: tuple,
    n_sims: int,
    seed: int | None,
) -> list[int]:
    """
    Run *n_sims* simulations, dispatching to either a single vectorised call
    or a multiprocessing pool depending on size.
    """
    if n_sims <= _PARALLEL_THRESHOLD:
        result = worker_fn((*extra_args, n_sims, seed))
        return result

    # Split into chunks across workers
    n_workers = _N_WORKERS or multiprocessing.cpu_count()
    chunk_size = max(1, n_sims // n_workers)
    chunks = []
    remaining = n_sims
    worker_seed = seed
    while remaining > 0:
        sz = min(chunk_size, remaining)
        chunks.append((*extra_args, sz, worker_seed))
        remaining -= sz
        if worker_seed is not None:
            worker_seed += 1   # different seed per chunk

    with multiprocessing.Pool(processes=n_workers) as pool:
        results = pool.map(worker_fn, chunks)

    # Flatten
    flat: list[int] = []
    for r in results:
        flat.extend(r)
    return flat


# ── Scope-growth / risk-adjusted variant ─────────────────────────────────────

def when_risk_adjusted(
    samples: list[int],
    backlog_low: int,
    backlog_high: int,
    n_sims: int = 10_000,
    confidence_levels: Sequence[int] = (50, 70, 85, 95),
    seed: int | None = None,
) -> McResult:
    """
    Risk-adjusted 'when' forecast.

    Models scope growth by drawing the effective backlog uniformly from
    [backlog_low, backlog_high] for each simulation.  This captures
    uncertainty about the final scope of the work.

    Parameters
    ----------
    backlog_low  : minimum expected backlog size
    backlog_high : maximum expected backlog size
    """
    if not samples or all(s == 0 for s in samples):
        return McResult(
            mode="when",
            n_simulations=n_sims,
            confidence_levels=list(confidence_levels),
            percentile_values={c: _MAX_PERIODS for c in confidence_levels},
            raw_samples=[],
        )

    rng = np.random.default_rng(seed)
    # Draw a backlog size for each simulation
    backlogs = rng.integers(backlog_low, backlog_high + 1, size=n_sims)

    raw: list[int] = []
    # Process in batches grouped by backlog size to benefit from vectorisation
    unique_bls, counts = np.unique(backlogs, return_counts=True)
    for bl, cnt in zip(unique_bls, counts):
        r = _vectorised_when(samples, int(bl), int(cnt),
                             seed=int(rng.integers(0, 2**31)) if seed is not None else None)
        raw.extend(r.tolist())

    pv = {int(c): int(np.percentile(raw, c)) for c in confidence_levels}

    return McResult(
        mode="when",
        n_simulations=n_sims,
        confidence_levels=list(confidence_levels),
        percentile_values=pv,
        raw_samples=raw,
    )
