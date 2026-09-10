"""Portable-session checks; never start Edge or contact Cloud."""

import contextlib
import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODES = ["binary", "multiline"]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class Feeds(unittest.TestCase):
    def test_feed_from_unrelated_working_directory(self):
        runtime = ROOT / ".runtime"
        runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=runtime) as unrelated:
            for mode in MODES:
                with self.subTest(mode=mode):
                    result = subprocess.run(
                        ["uv", "run", str(ROOT / "simulate.py"), mode, "--count", "10"],
                        cwd=unrelated,
                        capture_output=True,
                        check=True,
                    )
                    if mode == "binary":
                        self.assertEqual(result.stdout[:2], bytes.fromhex("1f8b"))
                        decoded = [
                            json.loads(line)
                            for line in gzip.decompress(result.stdout).splitlines()
                        ]
                        self.assertEqual(decoded, list(module("simulate").records(10)))
                    elif mode == "multiline":
                        events = result.stdout.decode().strip().split("\n\n")
                        self.assertEqual(len(events), 10)
                        for index, event in enumerate(events):
                            lines = event.splitlines()
                            self.assertEqual(len(lines), 5)
                            self.assertIn(f"sequence={index} ", lines[0])
                            self.assertTrue(lines[-1].startswith("Caused by:"))
                    else:
                        rows = result.stdout.decode().splitlines()
                        self.assertEqual(len(rows), 10)
                        self.assertEqual(rows[0], "0,pump-demo-07,60,WARN")
                        self.assertEqual(sum(row.endswith(",WARN") for row in rows), 2)

    def test_invalid_feed_arguments_rejected(self):
        for arguments in (
            [MODES[0], "--count", "0"],
            [MODES[0], "--interval", "-1"],
            ["csv"],
        ):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    ["uv", "run", str(ROOT / "simulate.py"), *arguments],
                    capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")

    def test_rehearsal_uses_only_session_files_from_unrelated_cwd(self):
        rehearsal = module("rehearse")
        runtime = ROOT / ".runtime"
        runtime.mkdir(exist_ok=True)
        real_parse = yaml.safe_load

        class StopBeforeEdge(Exception):
            pass

        for mode in MODES:
            with (
                self.subTest(mode=mode),
                tempfile.TemporaryDirectory(dir=runtime) as unrelated,
            ):

                def generate(argv, **kwargs):
                    self.assertEqual(
                        argv, ["uv", "run", str(ROOT / "simulate.py"), mode]
                    )
                    self.assertEqual(kwargs["cwd"], ROOT)
                    self.assertTrue(Path(kwargs["stdout"].name).is_relative_to(runtime))

                def inspect_config(text):
                    config = real_parse(text)
                    source = Path(config["input"]["file"]["paths"][0])
                    self.assertTrue(source.is_relative_to(runtime))
                    self.assertNotIn("${FEED_FILE}", text)
                    self.assertNotIn("${OUTPUT_FILE}", text)
                    raise StopBeforeEdge

                with (
                    contextlib.chdir(unrelated),
                    patch("sys.argv", ["rehearse.py", mode]),
                    patch.object(
                        rehearsal.subprocess, "run", side_effect=generate
                    ) as generated,
                    patch.object(
                        rehearsal.subprocess,
                        "Popen",
                        side_effect=AssertionError("No Edge in offline tests"),
                    ),
                    patch.object(
                        rehearsal.yaml, "safe_load", side_effect=inspect_config
                    ),
                    self.assertRaises(StopBeforeEdge),
                ):
                    rehearsal.main()
                generated.assert_called_once()


if __name__ == "__main__":
    unittest.main()
