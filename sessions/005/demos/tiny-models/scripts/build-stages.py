"""Rebuild pipelines/stage-2..4 from stage-1 and the pastes in pipelines/paste.

The stage files are what `just stage N` deploys; the pastes are what the
presenter pastes live. Building one from the other keeps them identical, and
tests/test_pipelines.py fails if anyone edits one without the other.
"""

from pathlib import Path

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
MARKER = "      # Paste each change above this line.\n"
CHANGE_2_ANCHOR = "      # Paste change 2 below change 1.\n"
PROCESSORS_START = "    processors:\n"
PROCESSORS_END = "      - mutation: root.left_node_at = now()\n"
PART_LINE = (
    '                        "part": {"type": "string", "enum": ["bearing", "seal", "motor",'
    ' "coupling", "strainer", "instrument", "valve", "none"]}'
)
SCHEMA_V3 = PART_LINE + '\n                      },\n                      "required": ["part"]\n'
SCHEMA_V4 = (
    PART_LINE
    + ',\n                        "problem_reported": {"type": "boolean"}\n'
    + '                      },\n                      "required": ["part", "problem_reported"]\n'
)


def paste(text: str, block: str) -> str:
    assert text.count(MARKER) == 1
    return text.replace(MARKER, block + MARKER)


def replace_processors(text: str, block: str) -> str:
    start = text.index(PROCESSORS_START)
    end = text.index(PROCESSORS_END, start) + len(PROCESSORS_END)
    return text[:start] + block + text[end:]


def build() -> dict[str, str]:
    stage1 = (PIPELINES / "stage-1.cloud.yaml").read_text()
    change1 = (PIPELINES / "paste" / "change-1.yaml").read_text()
    change2 = (PIPELINES / "paste" / "change-2.yaml").read_text()
    assert CHANGE_2_ANCHOR in change1
    assert change1 in change2
    stage2 = paste(stage1, change1)
    stage3 = replace_processors(stage2, change2)
    assert stage3.count(SCHEMA_V3) == 1
    stage4 = stage3.replace(SCHEMA_V3, SCHEMA_V4)
    return {
        "stage-2.cloud.yaml": stage2,
        "stage-3.cloud.yaml": stage3,
        "stage-4.cloud.yaml": stage4,
    }


if __name__ == "__main__":
    for name, text in build().items():
        (PIPELINES / name).write_text(text)
        print(f"wrote pipelines/{name}")
