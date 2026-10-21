"""Fit the Python model: an IsolationForest over three pump readings.

The forest learns what normal operation looks like from 2,000 readings drawn
around the same operating ranges the pipeline's generator uses for a healthy
pump. Anything far outside that envelope scores as an anomaly.

Run by `just warm` (and by `just up` if the model is missing). Writes
`.models/scorer.joblib` and `.models/scorer.json` beside this demo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

FEATURES = ("temp_c", "vibration_mm_s", "current_a")

# Centre and half-width of each reading on a healthy pump. These match the
# routine branch of the generator in pipelines/*.yaml, which spreads readings
# evenly across centre +/- half-width. Training draws from a bell curve whose
# +/- two standard deviations cover that band, so the edges of the healthy
# envelope are sparse and readings past them isolate quickly.
HEALTHY = {
    "temp_c": (62.0, 3.0),
    "vibration_mm_s": (2.8, 0.6),
    "current_a": (18.0, 1.5),
}

TREES = 32
ROWS = 2000
SEED = 5


def fit() -> IsolationForest:
    rng = np.random.default_rng(SEED)
    columns = [rng.normal(c, h / 2, ROWS) for c, h in (HEALTHY[f] for f in FEATURES)]
    readings = np.column_stack(columns)
    model = IsolationForest(
        n_estimators=TREES, max_samples=128, contamination=0.01, random_state=SEED
    )
    return model.fit(readings)


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model = fit()
    model_path = out_dir / "scorer.joblib"
    joblib.dump(model, model_path, compress=3)
    meta = {
        "model": "IsolationForest",
        "library": "scikit-learn",
        "features": list(FEATURES),
        "trees": TREES,
        "nodes": int(sum(tree.tree_.node_count for tree in model.estimators_)),
        "training_rows": ROWS,
        "bytes": model_path.stat().st_size,
    }
    (out_dir / "scorer.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"wrote {model_path} ({meta['bytes']} bytes, {meta['nodes']} nodes)")


if __name__ == "__main__":
    default = Path(__file__).resolve().parent.parent / ".models"
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
