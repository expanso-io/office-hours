import importlib.util
import random
from pathlib import Path

import feed
from scorer import train

ROOT = Path(__file__).resolve().parent.parent
PIPELINES = ROOT / "pipelines"
STAGES = {n: (PIPELINES / f"stage-{n}.cloud.yaml").read_text() for n in (1, 2, 3, 4)}


def load_build_stages():
    spec = importlib.util.spec_from_file_location(
        "build_stages", ROOT / "scripts" / "build-stages.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_stages_match_stage_1_plus_pastes():
    built = load_build_stages().build()
    for name, expected in built.items():
        assert (PIPELINES / name).read_text() == expected, f"{name} drifted from stage-1 + pastes"


def test_all_stages_are_revisions_of_one_job():
    for stage, text in STAGES.items():
        assert "name: office-hours-005-models\n" in text, stage
        assert "role: office-hours" in text, stage
        assert "threads: 1\n" in text, stage
        assert "address: 127.0.0.1:19501" in text, stage
        assert "path: /ingest" in text, stage
        assert "label: notes" in text, stage
        assert "127.0.0.1:19500/api/sink" in text, stage


def test_three_models_are_three_different_models_called_three_ways():
    assert "subprocess:" not in STAGES[1]
    assert "ollama_chat:" not in STAGES[1]
    assert "\n                    - http:\n" not in STAGES[1]

    assert "subprocess:" in STAGES[2] and "scorer/score.py" in STAGES[2]
    assert "deleted()" in STAGES[2]
    assert "ollama_chat:" not in STAGES[2]

    assert "ollama_chat:" in STAGES[3] and "qwen2.5:0.5b" in STAGES[3]
    assert (
        "http:" in STAGES[3] and "/v1/chat/completions" in STAGES[3] and "smollm2-360m" in STAGES[3]
    )
    assert "operator: set" in STAGES[3] and "operator: get" in STAGES[3]
    assert "root.last_note" in STAGES[3]
    assert "problem_reported" not in STAGES[3]
    assert '"problem_reported": {"type": "boolean"}' in STAGES[4]


def test_every_model_failure_is_caught_and_recorded():
    for stage in (3, 4):
        text = STAGES[stage]
        assert text.count("- catch:") == 4
        for key in ("python", "ollama", "direct"):
            assert f'root.{key} = {{"error": error()}}' in text
        assert "root.last_note = null" in text


def test_feed_healthy_ranges_and_fault_schedule_match_training():
    assert feed.HEALTHY == train.HEALTHY
    assert len(feed.NOTES) == 24
    assert feed.pump3_shift(10.0) == 0.0
    assert feed.pump3_rising(75.0) is True
    assert 0.4 < feed.pump3_shift(75.0) < 0.6
    assert feed.pump3_shift(100.0) == 1.0
    assert feed.pump1_spiking(50.0) is False
    assert feed.pump1_spiking(105.0) is True

    rng = random.Random(5)
    hot = feed.reading(rng, "pump-03", 100.0)
    assert hot["temp_c"] > 75.0 and hot["vibration_mm_s"] > 5.0
    spike = feed.reading(rng, "pump-01", 105.0)
    assert spike["current_a"] > 23.0

    notes = feed.Notes()
    rising_note = notes.next(65.0)
    assert rising_note == {"kind": "note", "asset": "pump-03", "text": feed.BEARING_NOTE}
    regular_note = notes.next(66.0)
    assert regular_note["asset"] != "pump-03"
    notes.cue("strainer")
    assert notes.next(70.0) == {"kind": "note", "asset": "pump-01", "text": feed.STRAINER_NOTE}
    assert notes.next(76.0) == {"kind": "note", "asset": "pump-03", "text": feed.BEARING_NOTE}
