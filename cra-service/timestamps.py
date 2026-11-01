"""Shared strict RFC 3339 syntax gate; Pydantic checks calendar validity."""

import re


def validate_timestamp(value):
    pattern = (
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt]"
        r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?"
        r"(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
    )
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError("timestamp must be an RFC 3339 date-time string with a timezone")
    return value
