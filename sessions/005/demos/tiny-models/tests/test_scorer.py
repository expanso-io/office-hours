import json

from scorer import score, train


def test_training_writes_a_tiny_model_and_its_description(tmp_path):
    train.main(tmp_path)
    meta = json.loads((tmp_path / "scorer.json").read_text())
    assert meta["model"] == "IsolationForest"
    assert meta["trees"] == train.TREES
    assert meta["bytes"] == (tmp_path / "scorer.joblib").stat().st_size
    assert meta["bytes"] < 200_000


def test_answers_follow_the_one_line_in_one_line_out_contract(tmp_path):
    train.main(tmp_path)
    model = score.load(tmp_path / "scorer.joblib")

    healthy = score.answer(model, '{"temp_c": 62, "vibration_mm_s": 2.8, "current_a": 18}')
    assert healthy["anomaly"] is False
    assert 0 < healthy["score"] < 1
    assert healthy["infer_ms"] >= 0

    overheating = score.answer(model, '{"temp_c": 81, "vibration_mm_s": 3.3, "current_a": 19.5}')
    assert overheating["anomaly"] is True
    assert overheating["score"] > healthy["score"]

    assert "error" in score.answer(model, '{"temp_c": 62}')
    assert "error" in score.answer(model, "not json")
    assert "error" in score.answer(model, "\n")
