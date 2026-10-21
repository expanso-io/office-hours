"""The feed: four pumps' readings and operator notes, POSTed to the edge node.

Readings arrive at 20 per second across pump-01..04 and notes every 6 seconds.
Two faults repeat on a fixed clock so they show up whenever a pipeline revision
lands:

  pump-03  60 s healthy, 30 s rising to 81 C and 6.2 mm/s, 30 s faulted, repeat
  pump-01  a 25 A current spike for 10 s in every 150 s

During each pump-03 rising phase one note reports its drive-end bearing.

Every POST the node answers with 2xx counts as admitted; its bytes count too.
The counters are written to .runtime/feed.json once a second, which is how the
cockpit knows records in. The rate can be changed while running by writing a
number to .runtime/feed-rate (see `just rate`).

Standard library only. Seeded, so two runs send the same values in the same
order.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import time
import urllib.error
import urllib.request
from pathlib import Path

ASSETS = ("pump-01", "pump-02", "pump-03", "pump-04")

# Centre and half-width of each reading on a healthy pump. scorer/train.py
# learns the same envelope.
HEALTHY = {"temp_c": (62.0, 3.0), "vibration_mm_s": (2.8, 0.6), "current_a": (18.0, 1.5)}

PUMP3_CYCLE = 120  # seconds: 0-60 healthy, 60-90 rising, 90-120 faulted
PUMP3_PEAK = {"temp_c": 81.0, "vibration_mm_s": 6.2}
PUMP1_CYCLE = 150  # seconds: current spike during 100-110
PUMP1_SPIKE = (100, 110)
PUMP1_SPIKE_AMPS = 25.0

NOTE_EVERY = 6.0
BEARING_NOTE = "Drive end bearing running hot and getting noisier."
STRAINER_NOTE = "Cleaned the suction strainer basket, differential pressure back to normal."
OTHER_ASSETS = ("pump-01", "pump-02", "pump-04")

# 24 notes, 18 routine and 6 describing a problem, cycled in this order.
NOTES = (
    STRAINER_NOTE,
    "Routine walkdown complete, motor and coupling guards secure.",
    "Shift handover complete, seal flush and sight glass normal.",
    "Drive end bearing rumbling and running hot.",
    "Visual check complete, discharge valve and gauge normal.",
    "Greased the drive end bearing as scheduled.",
    "Checked the seal flush line, flow is good.",
    "Mechanical seal weeping, small puddle under the pump.",
    "Motor cooling fins wiped down, no faults.",
    "Coupling guard refitted after inspection, all good.",
    "Pressure gauge reading matches the panel.",
    "Motor tripped on overload twice, smells burnt.",
    "Topped up oil to the sight glass mark.",
    "Area tidy, no leaks under the skid.",
    "Discharge valve exercised, moves freely.",
    "Coupling knocking at startup, guard is loose.",
    "Logged run hours, nothing unusual.",
    "Vibration pen check within limits.",
    "Panel lamps tested, all working.",
    "Suction strainer clogged, pump starting to cavitate.",
    "Pump room temperature normal, ventilation on.",
    "Swapped the duty pump as scheduled, both healthy.",
    "Night round complete, quiet shift.",
    "Flow transmitter reading zero while the pump runs.",
)


def pump3_shift(t: float) -> float:
    """0.0 when healthy, rising to 1.0 at the fault plateau."""
    phase = t % PUMP3_CYCLE
    if phase < 60:
        return 0.0
    if phase < 90:
        return (phase - 60) / 30
    return 1.0


def pump3_rising(t: float) -> bool:
    return 60 <= t % PUMP3_CYCLE < 90


def pump1_spiking(t: float) -> bool:
    return PUMP1_SPIKE[0] <= t % PUMP1_CYCLE < PUMP1_SPIKE[1]


def reading(rng: random.Random, asset: str, t: float) -> dict:
    values = {name: rng.gauss(centre, half / 2) for name, (centre, half) in HEALTHY.items()}
    if asset == "pump-03":
        shift = pump3_shift(t)
        for name, peak in PUMP3_PEAK.items():
            values[name] += shift * (peak - HEALTHY[name][0])
    if asset == "pump-01" and pump1_spiking(t):
        values["current_a"] = PUMP1_SPIKE_AMPS + rng.gauss(0, 0.4)
    return {
        "kind": "reading",
        "asset": asset,
        "temp_c": round(values["temp_c"], 1),
        "vibration_mm_s": round(values["vibration_mm_s"], 2),
        "current_a": round(values["current_a"], 1),
    }


class Notes:
    """Cycles the 24 notes, and slips in bearing notes when pump-03 is rising."""

    def __init__(self) -> None:
        self.index = 0
        self.last_bearing_cycle = -1
        self.queued: list[dict] = []

    def cue(self, kind: str) -> None:
        bearing = {"kind": "note", "asset": "pump-03", "text": BEARING_NOTE}
        strainer = {"kind": "note", "asset": "pump-01", "text": STRAINER_NOTE}
        self.queued = [strainer, bearing] if kind == "strainer" else [bearing]

    def next(self, t: float) -> dict:
        if self.queued:
            return self.queued.pop(0)
        cycle = int(t // PUMP3_CYCLE)
        if pump3_rising(t) and cycle != self.last_bearing_cycle:
            self.last_bearing_cycle = cycle
            return {"kind": "note", "asset": "pump-03", "text": BEARING_NOTE}
        text = NOTES[self.index % len(NOTES)]
        asset = OTHER_ASSETS[self.index % len(OTHER_ASSETS)]
        self.index += 1
        return {"kind": "note", "asset": asset, "text": text}


class Counters:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.admitted = {"reading": 0, "note": 0}
        self.bytes = 0
        self.refused = 0
        self.started = time.time()

    def write(self, rate: float) -> None:
        state = {
            "admitted": sum(self.admitted.values()),
            "admitted_readings": self.admitted["reading"],
            "admitted_notes": self.admitted["note"],
            "bytes": self.bytes,
            "refused": self.refused,
            "rate": rate,
            "started": self.started,
            "at": time.time(),
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(self.path)


def post(url: str, record: dict) -> int:
    body = json.dumps(record, separators=(",", ":")).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return len(body) if 200 <= response.status < 300 else -1
    except (urllib.error.URLError, OSError):
        return -1


def read_rate(path: Path, default: float) -> float:
    try:
        value = float(path.read_text().strip())
    except (OSError, ValueError):
        return default
    return value if 1 <= value <= 1000 else default


def pop_cue(path: Path) -> str | None:
    try:
        kind = path.read_text().strip()
        path.unlink()
        return kind or "bearing"
    except OSError:
        return None


def run(url: str, runtime: Path, rate: float, seed: int) -> None:
    rng = random.Random(seed)
    notes = Notes()
    counters = Counters(runtime / "feed.json")
    rate_file = runtime / "feed-rate"
    cue_file = runtime / "note-cue"
    stop = False

    def halt(*_args) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, halt)
    signal.signal(signal.SIGINT, halt)

    t0 = time.monotonic()
    t_offset = 45.0
    next_reading = t0
    next_note = t0 + NOTE_EVERY / 2
    next_write = t0
    sent = 0
    while not stop:
        now = time.monotonic()
        cue = pop_cue(cue_file)
        if cue:
            notes.cue(cue)
            next_note = min(next_note, now + 1.0)
            if (now - t0 + t_offset) % PUMP3_CYCLE < 60:
                t_offset = 65.0 - (now - t0) % PUMP3_CYCLE
        t = now - t0 + t_offset
        if now >= next_write:
            rate = read_rate(rate_file, rate)
            counters.write(rate)
            next_write = now + 1.0
        if now >= next_note:
            record = notes.next(t)
            next_note = now + NOTE_EVERY
        elif now >= next_reading:
            record = reading(rng, ASSETS[sent % len(ASSETS)], t)
            sent += 1
            # If the node was slow, do not try to make up a backlog.
            next_reading = max(next_reading + 1 / rate, now - 0.5)
        else:
            time.sleep(min(next_reading, next_note, next_write) - now)
            continue
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()) + (
            f".{int(time.time() * 1000) % 1000:03d}"
        )
        size = post(url, record)
        if size >= 0:
            counters.admitted[record["kind"]] += 1
            counters.bytes += size
        else:
            counters.refused += 1
    counters.write(rate)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:19501/ingest")
    parser.add_argument("--rate", type=float, default=20.0, help="readings per second")
    parser.add_argument("--seed", type=int, default=5)
    default_runtime = Path(__file__).resolve().parent / ".runtime"
    parser.add_argument(
        "--runtime", type=Path, default=Path(os.environ.get("OH5_RUNTIME", default_runtime))
    )
    args = parser.parse_args()
    args.runtime.mkdir(parents=True, exist_ok=True)
    run(args.url, args.runtime, args.rate, args.seed)


if __name__ == "__main__":
    main()
