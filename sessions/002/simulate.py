# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""Deterministic, finite synthetic feeds for Pipeline Office Hours."""

import argparse
import gzip
import json
import sys
import time


def records(count):
    for i in range(count):
        yield {
            "sequence": i,
            "sensor_id": "pump-demo-07",
            "temperature_c": 60 + i % 40,
            "status": "WARN" if i % 5 == 0 else "OK",
        }


def multiline(record):
    return (
        f"2026-09-07T10:00:00Z ERROR sequence={record['sequence']} service=checkout\n"
        "RuntimeError: synthetic payment timeout\n"
        '  File "checkout.py", line 42, in charge\n'
        "    provider.charge()\n"
        "Caused by: TimeoutError: provider did not respond\n\n"
    ).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["binary", "multiline"])
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval", type=float, default=0)
    args = parser.parse_args()
    if args.count < 1 or args.interval < 0:
        parser.error("count must be positive and interval nonnegative")
    for record in records(args.count):
        if args.mode == "binary":
            # Concatenated gzip members: real binary bytes, not base64 text.
            payload = gzip.compress((json.dumps(record) + "\n").encode(), mtime=0)
        else:
            payload = multiline(record)
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        if args.interval:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
