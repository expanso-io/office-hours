import re
from pathlib import Path

from scorer import train

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
STAGE1 = (PIPELINES / "stage-1-python.yaml").read_text()
STAGE2 = (PIPELINES / "stage-2-ollama.yaml").read_text()
STAGE3 = (PIPELINES / "stage-3-direct.yaml").read_text()

OLLAMA_START = "      # 2. Ollama."
DIRECT_START = "      # 3. Direct call."
TAIL = "      - mutation: root.done_at = now()"


def without_label(text: str) -> str:
    return re.sub(r'^  stage: ".*"$', "", text, flags=re.MULTILINE)


def test_each_stage_is_the_previous_one_plus_one_model():
    s3 = without_label(STAGE3)
    s2 = without_label(STAGE2)
    s1 = without_label(STAGE1)
    assert s2 == s3[: s3.index(DIRECT_START)] + s3[s3.index(TAIL) :]
    assert s1 == s2[: s2.index(OLLAMA_START)] + s2[s2.index(TAIL) :]


def test_all_stages_are_revisions_of_one_job():
    for text in (STAGE1, STAGE2, STAGE3):
        assert "name: office-hours-005-models\n" in text
        assert "role: office-hours" in text
        assert "count: 90\n" in text
        assert "threads: 1\n" in text


def test_three_models_are_three_different_models_called_three_ways():
    assert "subprocess:" in STAGE3 and "scorer/score.py" in STAGE3
    assert "ollama_chat:" in STAGE3 and "qwen2.5:0.5b" in STAGE3
    assert "http:" in STAGE3 and "/v1/chat/completions" in STAGE3 and "smollm2-135m" in STAGE3


def test_generator_healthy_ranges_match_the_training_ranges():
    centres = {
        "temp_c": r"\(\(62 \+ \$off\.index\(0\) \+ \(random_int\(seed: \d+, min: 0, max: (\d+)\) - (\d+)\) / 100\)",
        "vibration_mm_s": r"\(\(2\.8 \+ \$off\.index\(1\) \+ \(random_int\(seed: \d+, min: 0, max: (\d+)\) - (\d+)\) / 100\)",
        "current_a": r"\(\(18 \+ \$off\.index\(2\) \+ \(random_int\(seed: \d+, min: 0, max: (\d+)\) - (\d+)\) / 100\)",
    }
    for feature, pattern in centres.items():
        match = re.search(pattern, STAGE3)
        assert match, feature
        span, offset = int(match.group(1)), int(match.group(2))
        assert span == 2 * offset
        half_width = train.HEALTHY[feature][1]
        assert offset / 100 == half_width
    assert "(62 +" in STAGE3 and train.HEALTHY["temp_c"][0] == 62.0
    assert "(2.8 +" in STAGE3 and train.HEALTHY["vibration_mm_s"][0] == 2.8
    assert "(18 +" in STAGE3 and train.HEALTHY["current_a"][0] == 18.0


def test_every_model_failure_is_caught_and_recorded():
    assert STAGE3.count("- catch:") == 3
    for key in ("python", "ollama", "direct"):
        assert f'root.{key} = {{"error": error()}}' in STAGE3
