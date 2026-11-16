"""HW10: GEval evaluation of the HW8 pipeline, judge validation, tracing, and the Streamlit dashboard."""

import sys
from pathlib import Path

# Repo root (config, kafka_agents, backend) and Homework9 (hw9) must be importable whichever hw10 module is
# imported first; Ruff's import sorting does not know about sys.path order.
_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "scripts", _ROOT / "Homework9"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
