# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""Deterministic synthetic feeds for Pipeline Office Hours: finite or streaming.

By default writes a finite feed to stdout. With --count 0 it streams forever.
--send pushes the same bytes to a TCP listener (the pipeline's socket input) and
--tee appends them to a file so a second console can watch the raw bytes arrive.
"""

import argparse
import gzip
import json
import socket
import sys
import time


def records(count):
    i = 0
    while count == 0 or i < count:
        yield {
            "sequence": i,
            "sensor_id": "pump-demo-07",
            "temperature_c": 60 + i % 40,
            "status": "WARN" if i % 5 == 0 else "OK",
        }
        i += 1


def multiline(record):
    return (
        f"2026-09-07T10:00:00Z ERROR sequence={record['sequence']} service=checkout\n"
        "RuntimeError: synthetic payment timeout\n"
        '  File "checkout.py", line 42, in charge\n'
        "    provider.charge()\n"
        "Caused by: TimeoutError: provider did not respond\n\n"
    ).encode()


def connect(target, quiet):
    host, _, port = target.rpartition(":")
    while True:
        try:
            sock = socket.create_connection((host or "127.0.0.1", int(port)), timeout=5)
            sock.settimeout(None)
            if not quiet:
                print(f"connected to {target}", file=sys.stderr)
            return sock
        except OSError as error:
            if not quiet:
                print(f"waiting for {target}: {error}", file=sys.stderr)
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["binary", "multiline"])
    parser.add_argument("--count", type=int, default=10, help="0 streams forever")
    parser.add_argument("--interval", type=float, default=0)
    parser.add_argument("--send", metavar="HOST:PORT", help="push bytes over TCP")
    parser.add_argument("--tee", metavar="FILE", help="also append raw bytes here")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.count < 0 or args.interval < 0:
        parser.error("count must be nonnegative and interval nonnegative")
    if args.count == 0 and not args.interval:
        parser.error("streaming forever needs --interval")

    sink = connect(args.send, args.quiet) if args.send else None
    tee = open(args.tee, "ab") if args.tee else None
    try:
        for record in records(args.count):
            if args.mode == "binary":
                # Concatenated gzip members: real binary bytes, not base64 text.
                payload = gzip.compress((json.dumps(record) + "\n").encode(), mtime=0)
            else:
                payload = multiline(record)
            if sink is not None:
                try:
                    sink.sendall(payload)
                except OSError:
                    sink.close()
                    sink = connect(args.send, args.quiet)
                    sink.sendall(payload)
                if not args.quiet:
                    print(
                        f"sent sequence={record['sequence']} ({len(payload)} bytes)",
                        file=sys.stderr,
                    )
            else:
                sys.stdout.buffer.write(payload)
                sys.stdout.buffer.flush()
            if tee is not None:
                tee.write(payload)
                tee.flush()
            if args.interval:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        if sink is not None:
            sink.close()
        if tee is not None:
            tee.close()


if __name__ == "__main__":
    main()
