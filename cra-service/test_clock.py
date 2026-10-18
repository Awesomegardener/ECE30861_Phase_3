"""Check clock parsing against the shared schema without connecting to a database."""

import datetime

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from main import ClockUpdate
from pydantic import ValidationError


def clock_schema(contract):
    return Draft202012Validator(
        contract["paths"]["/api/v1/test/clock"]["put"]["requestBody"]["content"][
            "application/json"
        ]["schema"],
        format_checker=FormatChecker(),
    )


def test_clock_model_rejects_invalid_inputs(invalid_clock_input):
    # RFC 3339 does not allow trailing line terminators. The optional jsonschema
    # format checker accepts a final LF, so it is not the oracle for negative cases.
    with pytest.raises(ValidationError):
        ClockUpdate(now=invalid_clock_input)


def test_clock_model_preserves_valid_contract_inputs(contract, valid_clock_case):
    value, expected = valid_clock_case
    payload = {"now": value}
    clock_schema(contract).validate(payload)
    actual = ClockUpdate(**payload).now.astimezone(datetime.timezone.utc)
    assert actual.isoformat().replace("+00:00", "Z") == expected
