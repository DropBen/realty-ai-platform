"""Run deterministic evaluation fixtures without provider credentials."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from realty.evaluations import evaluate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(Path("evals/cases.json").read_text(encoding="utf-8"))
    results = [evaluate(case) for case in cases]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "Offline rules, evidence validation and schema safety. No live provider calls or model-quality measurement.",
        "passed": sum(item["passed"] for item in results),
        "total": len(results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Deterministic safety evaluations: {report['passed']}/{report['total']} passed")
    raise SystemExit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
