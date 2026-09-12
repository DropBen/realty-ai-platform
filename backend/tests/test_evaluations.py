import json
from pathlib import Path

import pytest
from realty.evaluations import evaluate

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "evals" / "cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_deterministic_safety_contract(case):
    assert evaluate(case)["passed"]
