#!/usr/bin/env python3
"""Thin CLI entry point for the disarmed DR01 walk test."""

from __future__ import annotations

import argparse
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description="DR01 disarmed perception walk test")
    parser.add_argument("--log", type=Path, help="append samples to a local CSV file")
    parser.add_argument("--interval", type=float, default=0.20, help="print interval in seconds")
    args = parser.parse_args()
    from sdfm.debug.walk import DEBUG_WALK_MODE, DebugWalkRunner, WalkSafetyViolation

    assert DEBUG_WALK_MODE is True
    try:
        DebugWalkRunner(csv_path=args.log).run(interval_sec=args.interval)
    except KeyboardInterrupt:
        return 0
    except WalkSafetyViolation as exc:
        print(f"SAFETY ABORT: {exc}")
        return 2
    except Exception as exc:
        print(f"WALK DEBUG FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
