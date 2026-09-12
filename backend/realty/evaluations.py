"""Offline, deterministic safety contracts; does not measure live model quality."""

from typing import Any

from pydantic import ValidationError

from realty.intelligence import evidence_supports_value, extract_demo
from realty.schemas import ActionInput, EmailPayload, Input, PreferenceInput


def evaluate(case: dict[str, Any]) -> dict[str, Any]:
    actual: Any
    kind = case["kind"]
    if kind == "extraction":
        result = extract_demo(case["text"])
        actual = {fact.field: fact.value for fact in result.facts}
        passed = actual == case["fields"] and all(
            fact.quote in case["text"] for fact in result.facts
        )
    elif kind == "evidence":
        actual = evidence_supports_value(case["value"], case["quote"])
        passed = actual == case["expected"]
    else:
        schemas: dict[str, type[Input]] = {
            "action_schema": ActionInput,
            "preference_schema": PreferenceInput,
            "email_schema": EmailPayload,
        }
        try:
            schemas[kind].model_validate(case["body"])
            actual = True
        except ValidationError:
            actual = False
        passed = actual == case["expected"]
    return {"id": case["id"], "category": kind, "passed": passed}
