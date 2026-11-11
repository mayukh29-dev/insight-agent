"""Run with python -m olist --source data/olist/raw --output data/olist/processed."""
import argparse
import json
from pathlib import Path

from .pipeline import ingest


def main():
    parser = argparse.ArgumentParser(description="Prepare historical Olist weekly BRL revenue")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    weekly, report = ingest(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    weekly.to_csv(args.output / "weekly_revenue.csv", index=False)
    (args.output / "quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
