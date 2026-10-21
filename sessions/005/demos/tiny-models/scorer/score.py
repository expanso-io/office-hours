"""Score pump readings, one JSON object per line on stdin, one answer per line on stdout.

The Expanso Edge `subprocess` processor starts this once and keeps it running,
so the model is loaded a single time and every record after that costs one
forest evaluation. Every input line gets exactly one output line, even when
the input is malformed, because the processor waits for an answer per record.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np

FEATURES = ("temp_c", "vibration_mm_s", "current_a")


def load(model_path: Path):
    return joblib.load(model_path)


def answer(model, line: str) -> dict:
    try:
        record = json.loads(line)
        row = np.array([[float(record[f]) for f in FEATURES]])
    except (ValueError, KeyError, TypeError) as exc:
        return {"error": f"bad input: {exc}"}
    started = time.perf_counter()
    # score_samples is higher for normal points; flip it so higher means stranger.
    score = float(-model.score_samples(row)[0])
    anomaly = bool(model.decision_function(row)[0] < 0)
    infer_ms = (time.perf_counter() - started) * 1000
    return {"anomaly": anomaly, "score": round(score, 3), "infer_ms": round(infer_ms, 3)}


def main() -> None:
    model_path = Path(__file__).resolve().parent.parent / ".models" / "scorer.joblib"
    if len(sys.argv) > 1:
        model_path = Path(sys.argv[1])
    model = load(model_path)
    for line in sys.stdin:
        sys.stdout.write(json.dumps(answer(model, line)) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
