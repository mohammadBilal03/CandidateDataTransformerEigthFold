#!/usr/bin/env python3
"""CLI for the Eightfold candidate profile ingestion engine.

Usage:
  python -m eightfold.cli --input file1.csv --input file2.json --input https://github.com/octocat \
      [--config config.json] [--out output.json]
"""
import argparse
import json
import sys

from .pipeline import run_pipeline


def main(argv=None):
    parser = argparse.ArgumentParser(description="Eightfold candidate profile ingestion engine")
    parser.add_argument("--input", action="append", required=True,
                         help="Path or URL to a source (repeatable). E.g. recruiter.csv, ats.json, "
                              "https://github.com/<user>, linkedin_export.json, resume.pdf, notes.txt")
    parser.add_argument("--config", help="Path to a runtime output config JSON file")
    parser.add_argument("--out", help="Path to write output JSON (default: stdout)")
    parser.add_argument("--pretty", action="store_true", default=True, help="Pretty-print JSON (default on)")
    parser.add_argument("--quiet", action="store_true", help="Suppress warnings/stats on stderr")
    args = parser.parse_args(argv)

    config = None
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)

    result = run_pipeline(args.input, config=config)

    output_json = json.dumps(result["profiles"], indent=2 if args.pretty else None, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output_json)
    else:
        print(output_json)

    if not args.quiet:
        print(f"\n--- stats: {result['stats']} ---", file=sys.stderr)
        for w in result["warnings"]:
            print(f"WARNING: {w}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
