"""Shared test setup.

OPENBLAS_NUM_THREADS=1 before any test imports numpy, for the same reason tools/export_app_data.py
sets it: the ARIMA fits are tiny, and OpenBLAS's default thread pool makes them several times
slower on a many-core machine. Results do not depend on it (bit-identical, measured on the 144-cell
grid). Subprocesses that the tests start inherit it. setdefault, so a caller can still override it.
"""

from __future__ import annotations

import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
