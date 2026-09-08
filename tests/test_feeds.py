import gzip
import json
import subprocess
import sys
import unittest

from simulate import multiline, records


class Feeds(unittest.TestCase):
    def test_binary_is_non_text_and_lossless(self):
        run = subprocess.run(
            [sys.executable, "simulate.py", "binary", "--count", "10"],
            capture_output=True,
            check=True,
        )
        self.assertEqual(run.stdout[:2], b"\x1f\x8b")
        decoded = [
            json.loads(line) for line in gzip.decompress(run.stdout).splitlines()
        ]
        self.assertEqual(decoded, list(records(10)))

    def test_nested_cause_is_part_of_each_trace(self):
        for record in records(10):
            lines = multiline(record).decode().strip().splitlines()
            self.assertEqual(len(lines), 5)
            self.assertTrue(lines[0].startswith("2026-09-07T"))
            self.assertTrue(lines[-1].startswith("Caused by:"))

    def test_invalid_count_rejected(self):
        result = subprocess.run(
            [sys.executable, "simulate.py", "binary", "--count", "0"],
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
