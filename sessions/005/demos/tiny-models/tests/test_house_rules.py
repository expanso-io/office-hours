"""House rules for everything in session 005: wording, engine, fonts, privacy."""

import re
from pathlib import Path

import pytest

SESSION = Path(__file__).resolve().parents[3]
DEMO = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", ".runtime", ".models", "__pycache__", ".pytest_cache", ".ruff_cache"}
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".html", ".css", ".js", ".toml"}
THIS_FILE = Path(__file__).resolve()


def session_files():
    for path in SESSION.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        wanted = path.suffix in TEXT_SUFFIXES or path.name in ("justfile", ".env.example")
        if path.is_file() and wanted and path.resolve() != THIS_FILE:
            yield path


def test_no_hedging_labels_on_screen_or_in_docs():
    banned = re.compile(
        r"\b(simulate|simulator|simulated|simulation|illustrative|sample|samples|modeled|modelled)\b",
        re.IGNORECASE,
    )
    hits = [
        f"{path.relative_to(SESSION)}:{n}: {line.strip()}"
        for path in session_files()
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if banned.search(line)
    ]
    assert hits == []


def test_expanso_edge_only():
    banned = re.compile(r"\b(benthos|bento|warpstream|bacalhau)\b", re.IGNORECASE)
    hits = [str(path) for path in session_files() if banned.search(path.read_text())]
    assert hits == []


def test_cockpit_fonts_are_bundled_plex_only():
    css = (DEMO / "cockpit" / "web" / "app.css").read_text()
    families = set(re.findall(r"font-family:\s*([^;]+);", css))
    assert families
    for family in families:
        assert (
            re.search(r"\b(Inter|Roboto|Arial|Helvetica|system-ui|-apple-system|Segoe)\b", family)
            is None
        )
        assert "IBM Plex" in family
    for font in re.findall(r'url\("/fonts/([^"]+)"\)', css):
        assert (DEMO / "cockpit" / "web" / "fonts" / font).is_file()


def test_no_version_pins_in_clone_and_run_commands():
    path = SESSION / "README.md"
    if not path.exists():
        pytest.skip("session README not written yet")
    readme = path.read_text()
    commands = "\n".join(re.findall(r"```(?:sh|bash)?\n(.*?)```", readme, re.DOTALL))
    assert re.search(r"\bv?\d+\.\d+\.\d+\b", commands) is None


def test_loopback_only_and_no_private_paths():
    for path in session_files():
        text = path.read_text()
        assert "0.0.0.0" not in text, path
        assert "/Users/" not in text, path
        assert "/home/" not in text, path
